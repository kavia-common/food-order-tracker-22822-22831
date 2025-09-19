from django.contrib import admin
from .models import Customer, Category, MenuItem, Order, OrderItem, Payment, OrderStatusEvent


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("full_name", "email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "position", "is_active", "created_at")
    list_editable = ("position", "is_active")
    search_fields = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_cents", "is_available", "is_active", "created_at")
    list_filter = ("category", "is_available", "is_active")
    search_fields = ("name", "category__name")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "status", "total_cents", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "customer__full_name", "customer__email")
    inlines = [OrderItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "method", "amount_cents", "currency", "created_at")
    list_filter = ("status", "method")


@admin.register(OrderStatusEvent)
class OrderStatusEventAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "at")
    list_filter = ("from_status", "to_status")
    search_fields = ("order__order_number",)
