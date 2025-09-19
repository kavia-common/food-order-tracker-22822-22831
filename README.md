# food-order-tracker-22822-22831

## Backend Database Setup

This project uses Django ORM as the storage layer. Default database is SQLite for development.

Basic commands:
- Install requirements: `pip install -r food_order_backend/requirements.txt`
- Run migrations:
  - `python food_order_backend/manage.py makemigrations`
  - `python food_order_backend/manage.py migrate`
- Create superuser (optional): `python food_order_backend/manage.py createsuperuser`
- Start server: `python food_order_backend/manage.py runserver 0.0.0.0:8000`

Admin is available at `/admin/`.

Models included:
- Customer, Category, MenuItem, Order, OrderItem, Payment, OrderStatusEvent

If switching to Postgres/MySQL, configure environment variables (see `food_order_backend/.env.example`) and update settings to read them.