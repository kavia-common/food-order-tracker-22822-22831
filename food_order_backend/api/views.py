from django.contrib.auth import login, logout
from django.views.decorators.csrf import csrf_exempt

from rest_framework import generics, permissions, status, serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.request import Request

from .models import Category, MenuItem, Order, OrderStatusEvent
from .serializers import (
    CategorySerializer,
    MenuItemSerializer,
    OrderSerializer,
    PlaceOrderSerializer,
    UpdateOrderStatusSerializer,
    AuthLoginSerializer,
    MeSerializer,
)


@api_view(["GET"])
def health(request: Request):
    """
    PUBLIC_INTERFACE
    Health check endpoint.

    Returns 200 OK when server is healthy.
    """
    return Response({"message": "Server is up!"})


# MENU LISTING

class CategoryListView(generics.ListAPIView):
    """
    PUBLIC_INTERFACE
    Lists active categories.

    GET /api/categories/
    """
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Category.objects.filter(is_active=True).order_by("position", "name")


class MenuItemListView(generics.ListAPIView):
    """
    PUBLIC_INTERFACE
    Lists available menu items, optionally filtered by category.

    Query params:
    - category_id (optional): filter by category
    """
    serializer_class = MenuItemSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = MenuItem.objects.filter(is_active=True, is_available=True).select_related("category")
        cid = self.request.query_params.get("category_id")
        if cid:
            qs = qs.filter(category_id=cid)
        return qs.order_by("category__position", "name")


# ORDERS

class PlaceOrderView(generics.GenericAPIView):
    """
    PUBLIC_INTERFACE
    Places a new order.

    POST /api/orders/
    Body:
      customer: {email, full_name, phone?, address?}
      items: [{menu_item_id, quantity}]
      special_instructions?: string
      delivery_fee_cents?: int

    Returns 201 with created order payload.
    """
    serializer_class = PlaceOrderSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request: Request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(generics.RetrieveAPIView):
    """
    PUBLIC_INTERFACE
    Retrieve an order by order_number.

    GET /api/orders/{order_number}/
    """
    lookup_field = "order_number"
    queryset = Order.objects.all().select_related("customer").prefetch_related("items__menu_item", "events")
    serializer_class = OrderSerializer
    permission_classes = [permissions.AllowAny]


class OrderStatusUpdateView(generics.UpdateAPIView):
    """
    PUBLIC_INTERFACE
    Update order status by order_number. Intended for staff usage.

    PATCH /api/orders/{order_number}/status/
    Body: { "status": "<new_status>" }
    """
    lookup_field = "order_number"
    queryset = Order.objects.all()
    serializer_class = UpdateOrderStatusSerializer
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request: Request, *args, **kwargs):
        order: Order = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(order, serializer.validated_data)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderEventsView(generics.ListAPIView):
    """
    PUBLIC_INTERFACE
    List status events for an order.

    GET /api/orders/{order_number}/events/
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.Serializer  # not used, we build a simple dict

    def list(self, request: Request, *args, **kwargs):
        order_number = kwargs.get("order_number")
        try:
            order = Order.objects.get(order_number=order_number)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        events = OrderStatusEvent.objects.filter(order=order).order_by("-at")
        payload = [
            {
                "from_status": e.from_status,
                "to_status": e.to_status,
                "at": e.at.isoformat(),
            }
            for e in events
        ]
        return Response(payload, status=status.HTTP_200_OK)


# AUTHENTICATION (session-based via Django)

@api_view(["POST"])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
@csrf_exempt
def auth_login(request: Request):
    """
    PUBLIC_INTERFACE
    Authenticate user via username/password and start a session.

    POST /api/auth/login/
    Body: { "username": "...", "password": "..." }

    Returns: { "user": {id, username, ...} }
    """
    serializer = AuthLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.validated_data["user"]
    login(request, user)
    return Response({"user": MeSerializer(user).data}, status=status.HTTP_200_OK)


@api_view(["POST"])
def auth_logout(request: Request):
    """
    PUBLIC_INTERFACE
    Logout the current user.

    POST /api/auth/logout/
    """
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def auth_me(request: Request):
    """
    PUBLIC_INTERFACE
    Get current user profile. Returns 401 if not authenticated.

    GET /api/auth/me/
    """
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(MeSerializer(request.user).data, status=status.HTTP_200_OK)
