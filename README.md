# Radha Backend

Radha Backend is a Django REST API for catering/event operations.  
It includes modules for event bookings, menu items and recipe ingredients, stock management, payments, expenses, vendors, users, and event staff assignment.

## Tech Stack

- Python
- Django
- Django REST Framework
- PostgreSQL
- Simple JWT (`djangorestframework-simplejwt`)
- CORS Headers

## Project Structure

```text
radha-backend/
|- radha/                  # Django project settings, root URLs, utils
|- user/                    # Authentication, users, notes, business profile
|- category/                # Food categories
|- item/                    # Menu items + recipe ingredient mapping
|- ListOfIngridients/       # Ingredient categories/items (legacy spelling in code)
|- stockmanagement/         # Stock categories/items + stock add/remove + alerts
|- eventbooking/            # Event booking + sessions + ingredient calculation
|- eventstaff/              # Staff, roles, waiter types, event staff assignment
|- payments/                # Payments and transaction history
|- Expense/                 # Expense categories/entities/expenses
|- vendor/                  # Vendors and vendor-category mapping
|- branchmanagement/        # Branch formats and invoice series
|- manage.py
|- requirements.txt
```

## Setup

### 1. Create and activate virtual environment

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure database

Current settings use PostgreSQL in `radha/settings.py`:

- DB Name: `radha`
- User: `postgres`
- Host: `localhost`
- Port: `5432`

Update these values for your local/server environment.

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Run development server

```bash
python manage.py runserver
```

Base API URL (default): `http://127.0.0.1:8000/api/`

## Authentication

- Custom login endpoint: `POST /api/login/`
- On successful login, response includes JWT tokens:
  - `tokens.access`
  - `tokens.refresh`
- Auth header format:

```http
Authorization: Bearer <access_token>
```

## API Modules and Endpoints

All endpoints below are under `/api/`.

### User

- `POST /login/`
- `POST /users/`
- `GET /users/`
- `DELETE /users/<uuid:id>/`
- `POST /change-password/<uuid:id>/`
- `POST /add-note/`
- `GET /get-note/`
- `PUT /update-note/<int:pk>/`
- `GET /business-profiles/`
- `POST /business-profiles/`
- `GET /business-profiles/<int:id>/`
- `PUT /business-profiles/<int:id>/`

### Category (menu categories)

- `GET /categories/`
- `POST /categories/`
- `GET /categories/<int:pk>/`
- `PUT /categories/<int:pk>/`
- `DELETE /categories/<int:pk>/`
- `POST /category-positions-changes/<int:pk>/`

### Item and Recipes

- `GET /items/`
- `POST /items/`
- `GET /items/<int:pk>/`
- `PUT /items/<int:pk>/`
- `DELETE /items/<int:pk>/`
- `GET /recipes/`
- `POST /recipes/`
- `GET /recipes/<int:pk>/`
- `PUT /recipes/<int:pk>/`
- `DELETE /recipes/<int:pk>/`
- `GET /recipes/item/<int:item_id>/`

### Ingredients (`ListOfIngridients`)

Legacy + canonical endpoints both exist.

- `GET|POST /ingridients-categories/`
- `GET|PUT|DELETE /ingridients-categories/<int:pk>/`
- `GET|POST /ingridients-item/`
- `GET|PUT|DELETE /ingridients-item/<int:pk>/`
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

Notes:
- Event session dates use `DD-MM-YYYY`.
- Ingredient requirement is dynamically computed from selected items and recipe mapping.

### Stock Management

- `GET|POST /stoke-categories/`
- `GET|PUT|DELETE /stoke-categories/<int:pk>/`
- `GET|POST /stoke-items/`
- `GET|PUT|DELETE /stoke-items/<int:pk>/`
- `POST /add-stoke-item/` (remove quantity)
- `PUT /add-stoke-item/` (add quantity)
- `GET /alert-stoke-item/`

### Payments

- `GET|POST /parties/`
- `GET|PUT|PATCH|DELETE /parties/<int:pk>/`
- `GET|POST /payments/`
- `GET|PUT|DELETE /payments/<int:pk>/`
- `GET /all-transaction/`

Notes:
- `payment_date` uses `DD-MM-YYYY`.
- Transaction history is automatically created for payment updates.
- Payments now support `party_id`, `party_name`, `party_gst_no`, and `party_code`.

### Expense

- `GET|POST /expenses/`
- `GET|PUT|DELETE /expenses/<int:pk>/`
- `GET|POST /expenses-categories/`
- `GET|PUT|DELETE /expenses-categories/<int:pk>/`
- `GET|POST /entities/`
- `GET|PUT|DELETE /entities/<int:pk>/`
- `GET /entities/<int:pk>/summary/?period=all|month|year`

### Vendor

- `GET|POST /vendors/`
- `GET|PUT|DELETE /vendors/<int:pk>/`
- `GET|POST /categories/`
- `GET|PUT|DELETE /categories/<int:pk>/`

### Branch Formats & Invoice Series

- `GET|POST /invoice-setup/`
- `GET|PUT|PATCH|DELETE /invoice-setup/<int:pk>/`
- `GET|POST /party-information/`
- `GET|PUT|PATCH|DELETE /party-information/<int:pk>/`

Notes:
- Use `invoice_prefix` like `MBR26-`.
- `invoice-setup` stores branch details like branch name, address, and branch GST number.
- `party-information` stores party details plus `invoice_prefix` and `next_sequence_no`.
- `party-information` response includes `next_invoice_preview`, for example `MBR26-163`.
- `party-information` supports `search` and `is_active` query params.
- If `party_code` is not sent, it is auto-generated as a numeric code like `1001`.

### Event Staff

- `GET|POST /roles/`
- `GET|PUT|PATCH|DELETE /roles/<int:pk>/`
- `GET|POST /waiter-types/`
- `GET|PUT|PATCH|DELETE /waiter-types/<int:pk>/`
- `GET|POST /staff/`
- `GET|PUT|PATCH|DELETE /staff/<int:pk>/`
- `GET /staff/waiters/`
- `GET|POST /event-assignments/`
- `GET|PUT|PATCH|DELETE /event-assignments/<int:pk>/`
- `GET /event-assignments/event-summary/`

## Data Model Overview

Main entities:

- `UserModel` (custom auth user, UUID primary key)
- `EventBooking` -> has many `EventSession`
- `Item` -> has many `RecipeIngredient`
- `RecipeIngredient` -> links `Item` and `IngridientsItem`
- `StokeItem` -> belongs to `StokeCategory`
- `Payment` -> belongs to `EventBooking`, has many `TransactionHistory`
- `Expense` -> belongs to `Expense Category`, optional `ExpenseEntity`
- `Vendor` -> mapped to ingredient categories via `VendorCategory`
- `BranchFormat` -> stores branch details and invoice sequence configuration
- `Staff`, `StaffRole`, `WaiterType`, `EventStaffAssignment`

## Existing Script

- `radha-beckend.sh` starts Gunicorn:

```bash
gunicorn radha.wsgi:application --bind 127.0.0.1:8005
```

## Postman

A collection exists at:

- `radha.postman_collection.json`

Import it into Postman to test endpoints quickly.

## Known Issues / Important Notes

- Route collision: both `category` and `vendor` apps register `/api/categories/` and `/api/categories/<int:pk>/`.  
  Because `category.urls` is included first in `radha/urls.py`, vendor category routes may be shadowed.
- Sensitive values (secret key and DB credentials) are currently hardcoded in `radha/settings.py`. Move these to environment variables for production.
- The code comments in settings mention Django 4.2, while `requirements.txt` pins Django 5.1.4.
