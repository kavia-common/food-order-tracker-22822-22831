from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator

# Note: If the project later introduces Django auth Users, we can add a ForeignKey to settings.AUTH_USER_MODEL.


class TimeStampedModel(models.Model):
    """
    Abstract base model that tracks creation and update timestamps.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    Abstract base model that supports soft deletion.
    """
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


# PUBLIC_INTERFACE
class Customer(TimeStampedModel, SoftDeleteModel):
    """Customer information for placing orders."""
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(regex=r"^[0-9+\-() ]+$", message="Invalid phone number format")],
    )
    default_address = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"


# PUBLIC_INTERFACE
class Category(TimeStampedModel, SoftDeleteModel):
    """Menu category (e.g., Pizza, Drinks)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0, help_text="Order for display in menus")

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


# PUBLIC_INTERFACE
class MenuItem(TimeStampedModel, SoftDeleteModel):
    """A menu item that can be ordered by customers."""
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="items")
    name = models.CharField(max_length=150, db_index=True)
    description = models.TextField(blank=True)
    price_cents = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
        help_text="Price stored in cents to avoid floating point errors",
    )
    image_url = models.URLField(blank=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = [("category", "name")]
        indexes = [
            models.Index(fields=["is_available", "category"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (${self.price_cents/100:.2f})"


# PUBLIC_INTERFACE
class Order(TimeStampedModel):
    """Represents a customer order and its lifecycle."""
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        PREPARING = "PREPARING", "Preparing"
        READY = "READY", "Ready for pickup/delivery"
        OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", "Out for delivery"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    order_number = models.CharField(max_length=20, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    special_instructions = models.TextField(blank=True)
    subtotal_cents = models.PositiveIntegerField(default=0)
    tax_cents = models.PositiveIntegerField(default=0)
    delivery_fee_cents = models.PositiveIntegerField(default=0)
    total_cents = models.PositiveIntegerField(default=0)
    eta = models.DateTimeField(null=True, blank=True, help_text="Estimated time of completion")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    # PUBLIC_INTERFACE
    def recalculate_totals(self) -> None:
        """Recalculate subtotal, tax, and total based on line items."""
        items = self.items.all()
        subtotal = sum(i.quantity * i.unit_price_cents for i in items)
        self.subtotal_cents = subtotal
        # Example simple tax rule 8% (can be externalized later via env/config)
        tax = int(round(subtotal * 0.08))
        self.tax_cents = tax
        self.total_cents = subtotal + tax + self.delivery_fee_cents

    # PUBLIC_INTERFACE
    def mark_status(self, new_status: str) -> None:
        """Update order status safely."""
        if new_status not in Order.Status.values:
            raise ValueError("Invalid status")
        self.status = new_status

    def __str__(self) -> str:
        return f"Order {self.order_number} - {self.customer.full_name} - {self.status}"


# PUBLIC_INTERFACE
class OrderItem(TimeStampedModel):
    """A line item within an order."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    unit_price_cents = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
        help_text="Captured at time of order to preserve historical pricing",
    )

    class Meta:
        unique_together = [("order", "menu_item")]
        indexes = [
            models.Index(fields=["order"]),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.menu_item.name} ({self.order.order_number})"


# PUBLIC_INTERFACE
class Payment(TimeStampedModel):
    """Payment records associated with an order."""
    class Method(models.TextChoices):
        CARD = "CARD", "Credit/Debit Card"
        CASH = "CASH", "Cash"
        WALLET = "WALLET", "Wallet/UPI"

    class Status(models.TextChoices):
        INITIATED = "INITIATED", "Initiated"
        AUTHORIZED = "AUTHORIZED", "Authorized"
        CAPTURED = "CAPTURED", "Captured"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CARD)
    amount_cents = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=10, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIATED, db_index=True)
    processor_ref = models.CharField(max_length=100, blank=True, help_text="Reference from payment processor, if any")

    def __str__(self) -> str:
        return f"Payment {self.status} - {self.amount_cents/100:.2f} {self.currency} for {self.order.order_number}"


# PUBLIC_INTERFACE
class OrderStatusEvent(TimeStampedModel):
    """
    Event log for order status changes to help with real-time tracking and analytics.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, choices=Order.Status.choices)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at"]
        indexes = [
            models.Index(fields=["order", "at"]),
        ]

    def __str__(self) -> str:
        return f"{self.order.order_number}: {self.from_status} -> {self.to_status} at {self.at.isoformat()}"
