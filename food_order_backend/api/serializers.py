from typing import List
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Category, MenuItem, Order, OrderItem, Payment, Customer, OrderStatusEvent


# PUBLIC_INTERFACE
class CategorySerializer(serializers.ModelSerializer):
    """Category serializer for listing categories."""

    class Meta:
        model = Category
        fields = ["id", "name", "description", "position", "is_active"]


# PUBLIC_INTERFACE
class MenuItemSerializer(serializers.ModelSerializer):
    """Menu Item serializer for listing menu items."""

    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True), source="category", write_only=True, required=False
    )

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "name",
            "description",
            "price_cents",
            "image_url",
            "is_available",
            "is_active",
            "category",
            "category_id",
        ]
        read_only_fields = ["is_active", "category"]


class OrderItemInlineSerializer(serializers.ModelSerializer):
    """Inline read serializer for order items (used inside OrderSerializer)."""

    menu_item = MenuItemSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "menu_item", "quantity", "unit_price_cents", "created_at"]


class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer for order payment record."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "amount_cents",
            "currency",
            "status",
            "processor_ref",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "created_at", "updated_at"]


# PUBLIC_INTERFACE
class OrderSerializer(serializers.ModelSerializer):
    """Order serializer for reading order information."""

    items = OrderItemInlineSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "special_instructions",
            "subtotal_cents",
            "tax_cents",
            "delivery_fee_cents",
            "total_cents",
            "eta",
            "customer_name",
            "customer_email",
            "items",
            "payment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "order_number",
            "subtotal_cents",
            "tax_cents",
            "total_cents",
            "created_at",
            "updated_at",
            "status",
        ]


class OrderItemCreateSerializer(serializers.Serializer):
    """Write serializer for creating order items."""

    menu_item_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuItem.objects.filter(is_active=True, is_available=True),
        source="menu_item",
    )
    quantity = serializers.IntegerField(min_value=1, max_value=100)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        # Attach current price snapshot to be stored as unit_price_cents
        menu_item: MenuItem = value["menu_item"]
        value["unit_price_cents"] = menu_item.price_cents
        return value


# PUBLIC_INTERFACE
class PlaceOrderSerializer(serializers.Serializer):
    """
    Write serializer for placing a new order.

    Expects:
    - customer: object with email, full_name, phone (optional), address (optional)
    - items: array of {menu_item_id, quantity}
    - special_instructions: string (optional)
    """

    customer = serializers.DictField(child=serializers.CharField(), allow_empty=False)
    items = OrderItemCreateSerializer(many=True)
    special_instructions = serializers.CharField(required=False, allow_blank=True)
    delivery_fee_cents = serializers.IntegerField(required=False, min_value=0, default=0)

    def validate_customer(self, value: dict) -> dict:
        email = value.get("email")
        full_name = value.get("full_name")
        if not email or not full_name:
            raise serializers.ValidationError("customer.email and customer.full_name are required")
        return value

    def create(self, validated_data):
        from django.db import transaction
        from django.utils.crypto import get_random_string

        customer_data = validated_data["customer"]
        items_data: List[dict] = validated_data["items"]
        special_instructions = validated_data.get("special_instructions", "")
        delivery_fee_cents = validated_data.get("delivery_fee_cents", 0)

        # Upsert Customer by email
        customer, _ = Customer.objects.get_or_create(
            email=customer_data["email"],
            defaults={
                "full_name": customer_data.get("full_name", ""),
                "phone": customer_data.get("phone", ""),
                "default_address": customer_data.get("address", ""),
            },
        )
        # If exists, update name/phone/address if provided
        updated = False
        if customer_data.get("full_name") and customer.full_name != customer_data["full_name"]:
            customer.full_name = customer_data["full_name"]; updated = True
        if "phone" in customer_data and customer.phone != customer_data.get("phone", ""):
            customer.phone = customer_data.get("phone", ""); updated = True
        if "address" in customer_data and customer.default_address != customer_data.get("address", ""):
            customer.default_address = customer_data.get("address", ""); updated = True
        if updated:
            customer.save()

        with transaction.atomic():
            order_number = get_random_string(10).upper()
            order = Order.objects.create(
                order_number=order_number,
                customer=customer,
                special_instructions=special_instructions,
                delivery_fee_cents=delivery_fee_cents,
            )
            # Create items
            for item in items_data:
                OrderItem.objects.create(order=order, **item)
            # Totals
            order.recalculate_totals()
            order.save()
            # Initial payment record (initiated)
            Payment.objects.create(
                order=order,
                method=Payment.Method.CARD,
                amount_cents=order.total_cents,
                currency="USD",
                status=Payment.Status.INITIATED,
            )
            # First status event
            OrderStatusEvent.objects.create(
                order=order, from_status=Order.Status.PENDING, to_status=Order.Status.PENDING
            )
        return order


# PUBLIC_INTERFACE
class UpdateOrderStatusSerializer(serializers.Serializer):
    """Serializer for updating an order status; records status transition event."""

    status = serializers.ChoiceField(choices=Order.Status.choices)

    def update(self, instance: Order, validated_data):
        new_status = validated_data["status"]
        old_status = instance.status
        if new_status == old_status:
            return instance
        instance.mark_status(new_status)
        instance.save(update_fields=["status", "updated_at"])
        OrderStatusEvent.objects.create(order=instance, from_status=old_status, to_status=new_status)
        return instance


# PUBLIC_INTERFACE
class AuthLoginSerializer(serializers.Serializer):
    """Serializer for authenticating a user and returning a session-style response."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs["username"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid credentials")
        attrs["user"] = user
        return attrs


# PUBLIC_INTERFACE
class MeSerializer(serializers.ModelSerializer):
    """Serializer returning minimal user profile."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_staff", "is_superuser"]
