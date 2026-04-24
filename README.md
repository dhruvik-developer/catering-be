# Radha Backend

Radha Backend is a Django REST API for catering and event operations.  
It includes user/auth, permissions, bookings, inventory, ingredients, vendors, expenses, payments, event staff, and ground management.

## Tech Stack

- Python
- Django `5.1.4`
- Django REST Framework `3.15.2`
- Simple JWT (`djangorestframework-simplejwt`)
- django-filter
- django-cors-headers
- Pillow
- Gunicorn
- Database currently configured in code: SQLite (`db.sqlite3`)

## Project Structure

```text
radha-be/
|- radha/                   # Django project settings, root URLs, middleware, utils
|- accesscontrol/           # Access-control modules and user permission assignments
|- user/                    # Auth/login, users, notes, business profile
|- category/                # Menu categories
|- item/                    # Menu items and recipe ingredient mapping
|- ListOfIngridients/       # Ingredient categories/items (legacy spelling kept)
|- stockmanagement/         # Stock categories/items and quantity operations
|- eventbooking/            # Event bookings, sessions, item configs, vendor assignments
|- eventstaff/              # Roles, staff, waiter types, assignments, salary/withdrawals
|- groundmanagement/        # Ground categories/items
|- payments/                # Payments and transactions
|- Expense/                 # Expenses, expense categories, entities
|- vendor/                  # Vendors and vendor categories
|- branchmanagement/        # Present in repo, currently NOT wired in urls/settings
|- media/                   # Uploaded media files
|- manage.py
|- requirements.txt
|- .env.example
|- radha-beckend.sh
```

## Setup

### 1. Create and activate virtual environment

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill values:

```bash
cp .env.example .env
```

PowerShell alternative:

```powershell
Copy-Item .env.example .env
```

Main variables:

- `SERVER`
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CORS_ALLOW_ALL_ORIGINS`
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (template values; DB env block is currently commented in settings)
- `JWT_SIGNING_KEY`

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Sync permissions

Radha Backend automatically generates standard CRUD permissions (view, create, update, delete) for all custom models. To populate the database with these permissions, run:

```bash
python manage.py sync_permissions
```

To preview the generated permission catalog JSON without saving:

```bash
python manage.py sync_permissions --print-catalog
```

### 6. Run development server

```bash
python manage.py runserver
```

Base URL: `http://127.0.0.1:8000`  
API prefix: `/api/`

## Authentication

- Login endpoint: `POST /api/login/`
- JWT header:

```http
Authorization: Bearer <access_token>
```

## API Modules and Endpoints

All routes are under `/api/`.

### Access Control

- `GET /access-control/modules/`
- `GET /access-control/users/`
- `GET|PUT /access-control/users/<uuid:user_id>/permissions/`
- `GET /me/permissions/`

### User

- `POST /login/`
- `POST|GET /users/`
- `DELETE /users/<uuid:id>/`
- `POST /change-password/<uuid:id>/`
- `POST|GET /add-note/` and `/get-note/`
- `PUT /update-note/<int:pk>/`
- `GET|POST /business-profiles/`
- `GET|PUT /business-profiles/<int:id>/`

### Category (Menu)

- `GET|POST /categories/`
- `GET|PUT|DELETE /categories/<int:pk>/`
- `POST /category-positions-changes/<int:pk>/`

### Item and Recipes

- `GET|POST /items/`
- `GET|PUT|DELETE /items/<int:pk>/`
- `GET|POST /recipes/`
- `GET|PUT|DELETE /recipes/<int:pk>/`
- `GET /recipes/item/<int:item_id>/`

### Ingredients (`ListOfIngridients`)
- `GET|POST /ingredients-categories/`
- `GET|PUT|DELETE /ingredients-categories/<int:pk>/`
- `GET|POST /ingredients-items/`
- `GET|PUT|DELETE /ingredients-items/<int:pk>/`

### Event Booking

- `GET|POST /event-bookings/`
- `GET|PUT|DELETE /event-bookings/<int:pk>/`
- `POST /status-change-event-bookings/<int:pk>/`
- `GET /pending-event-bookings/`
- `GET /get-all/`
- `GET /session-ingredients/`
- `GET|POST /event-item-configs/`
- `GET|PUT|PATCH|DELETE /event-item-configs/<int:pk>/`
- `GET|POST /ingredient-vendor-assignments/`
- `GET|PUT|PATCH|DELETE /ingredient-vendor-assignments/<int:pk>/`

### Stock Management

- `GET|POST /stoke-categories/`
- `GET|PUT|DELETE /stoke-categories/<int:pk>/`
- `GET|POST /stoke-items/`
- `GET|PUT|DELETE /stoke-items/<int:pk>/`
- `POST|PUT /add-stoke-item/`
- `GET /alert-stoke-item/`

### Payments

- `GET|POST /payments/`
- `GET|PUT|DELETE /payments/<int:pk>/`
- `GET /all-transaction/`

### Expense

- `GET|POST /expenses/`
- `GET|PUT|DELETE /expenses/<int:pk>/`
- `GET|POST /expenses-categories/`
- `GET|PUT|DELETE /expenses-categories/<int:pk>/`
- `GET|POST /entities/`
- `GET|PUT|DELETE /entities/<int:pk>/`
- `GET /entities/<int:pk>/summary/`

### Vendor

- `GET|POST /vendors/`
- `GET|PUT|DELETE /vendors/<int:pk>/`
- `GET|POST /categories/`
- `GET|PUT|DELETE /categories/<int:pk>/`

### Event Staff

- `GET|POST /roles/`
- `GET|PUT|PATCH|DELETE /roles/<int:pk>/`
- `GET|POST /staff/`
- `GET|PUT|PATCH|DELETE /staff/<int:pk>/`
- `GET /staff/waiters/`
- `GET /staff/<int:pk>/fixed-payment-summary/`
- `GET|POST /waiter-types/`
- `GET|PUT|PATCH|DELETE /waiter-types/<int:pk>/`
- `GET|POST /event-assignments/`
- `GET|PUT|PATCH|DELETE /event-assignments/<int:pk>/`
- `GET /event-assignments/event-summary/`
- `GET|POST /fixed-salary-payments/`
- `GET|PUT|PATCH|DELETE /fixed-salary-payments/<int:pk>/`
- `GET|POST /staff-withdrawals/`
- `GET|PUT|PATCH|DELETE /staff-withdrawals/<int:pk>/`

### Ground Management

- `GET|POST /ground/categories/`
- `GET|PUT|PATCH|DELETE /ground/categories/<int:pk>/`
- `GET|POST /ground/items/`
- `GET|PUT|PATCH|DELETE /ground/items/<int:pk>/`

### Branch Management (Currently Disabled)

These routes exist in `branchmanagement/urls.py` but are currently commented out in `radha/urls.py` and `radha/settings.py`:

- `/invoice-setup/`
- `/party-information/`
- `/global-config/`
- `/branch-items/`
- `/branch-bills/`

## Deployment Script

`radha-beckend.sh` does:

1. Activate venv (if present)
2. Run migrations
3. Start Gunicorn with `radha.wsgi:application`

Default bind: `127.0.0.1:8006`

## Important Notes

- Route collision exists on `/api/categories/` and `/api/categories/<int:pk>/` between `category` and `vendor`.
  `category.urls` is included first in `radha/urls.py`, so vendor category endpoints can be shadowed.
- `CORS_ALLOW_ALL_ORIGINS` defaults to `True` in settings; tighten this in production.
- `branchmanagement` is present but not active in installed apps and root URLs.
- README no longer references a Postman collection file because `radha.postman_collection.json` is not present in this repository.
