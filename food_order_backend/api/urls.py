from django.urls import path
from .views import (
    health,
    CategoryListView,
    MenuItemListView,
    PlaceOrderView,
    OrderDetailView,
    OrderStatusUpdateView,
    OrderEventsView,
    auth_login,
    auth_logout,
    auth_me,
)

urlpatterns = [
    # Health
    path("health/", health, name="Health"),

    # Menu
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("menu-items/", MenuItemListView.as_view(), name="menuitem-list"),

    # Orders
    path("orders/", PlaceOrderView.as_view(), name="order-create"),
    path("orders/<str:order_number>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<str:order_number>/status/", OrderStatusUpdateView.as_view(), name="order-status-update"),
    path("orders/<str:order_number>/events/", OrderEventsView.as_view(), name="order-events"),

    # Auth
    path("auth/login/", auth_login, name="auth-login"),
    path("auth/logout/", auth_logout, name="auth-logout"),
    path("auth/me/", auth_me, name="auth-me"),
]
