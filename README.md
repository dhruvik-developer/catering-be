# Radha Backend

Radha Backend is a Django REST API for catering and event operations.  
It includes user/auth, permissions, bookings, inventory, ingredients, vendors, expenses, payments, event staff, and ground management.

For the current end-to-end project flow, module responsibilities, active API
routes, admin coverage, and inactive module notes, see
[`CURRENT_FLOW.md`](CURRENT_FLOW.md).

## Tech Stack

- Python
- Django `5.2.13`
- Django REST Framework `3.15.2`
- Simple JWT (`djangorestframework-simplejwt`)
- django-filter
- django-cors-headers
- Pillow
- Gunicorn
- SQLite for local development, PostgreSQL for SaaS tenant schemas

## Project Structure

```text
radha-be/
|- radha/                   # Django project settings, root URLs, middleware, utils
|- tenancy/                 # django-tenants client/domain/subscription management
|- accesscontrol/           # Access-control modules and user permission assignments
|- user/                    # Auth/login, users, notes, business profile
|- category/                # Menu categories
|- item/                    # Menu items and recipe ingredient mapping
|- ListOfIngridients/       # Ingredient categories/items (legacy spelling kept)
|- stockmanagement/         # Stock categories/items and quantity operations
|- eventbooking/            # Event bookings, sessions, item configs, vendor assignments
|- pdfformatter/            # Stored HTML templates used for PDF formatter views
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
- `CORS_ALLOWED_ORIGIN_REGEXES`
- `CORS_ALLOW_ALL_ORIGINS`
- `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `SAAS_ROOT_DOMAIN`
- `SHOW_PUBLIC_IF_NO_TENANT_FOUND`
- `JWT_SIGNING_KEY`

### 4. Apply migrations

```bash
python manage.py migrate_schemas --shared
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
python manage.py runserver 0.0.0.0:8000
```

Base URL: `http://admin.localhost:8000` or `http://client1.localhost:8000`  
API prefix: `/api/`

## Authentication

- Login endpoint: `POST /api/login/`
- JWT header:

```http
Authorization: Bearer <access_token>
```

## SaaS / Tenant Mode

The backend uses `django-tenants` for subdomain-based PostgreSQL schema isolation:

- `admin.trayza.in` maps to the `public` schema for platform superadmin work.
- `client1.trayza.in` maps to schema `client1`.
- Tenant business data is isolated by PostgreSQL `search_path`; API views should not manually filter by `tenant_id`.
- Login is tenant-aware because the subdomain resolves the schema before authentication.
- JWTs include `schema_name` and are rejected on the wrong tenant host.

For PostgreSQL schema-per-tenant mode, set:

```env
DB_ENGINE=django_tenants.postgresql_backend
DB_NAME=radha
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
SAAS_ROOT_DOMAIN=trayza.in
SHOW_PUBLIC_IF_NO_TENANT_FOUND=False
```

Local hosts file for subdomain testing on Windows:

```text
127.0.0.1 admin.localhost
127.0.0.1 client1.localhost
127.0.0.1 client2.localhost
```

Bootstrap public and default tenant domains:

```powershell
python manage.py migrate_schemas --shared
python manage.py bootstrap_saas --public-domain admin.localhost --default-schema client1 --default-domain client1.localhost --default-name "Client 1"
python manage.py sync_permissions
```

For an existing single-tenant database, copy current public business rows into the default tenant schema after the tenant exists:

```powershell
python manage.py copy_public_to_tenant --schema client1 --dry-run
python manage.py copy_public_to_tenant --schema client1
python manage.py migrate_schemas --tenant
```

Create a tenant and its first tenant admin:

```http
POST /api/tenants/
Authorization: Bearer <platform-superadmin-token>
Content-Type: application/json

{
  "name": "Radha Catering",
  "schema_name": "radha",
  "domain": "radha.trayza.in",
  "subscription_status": "active",
  "enabled_modules": ["categories", "items", "event_bookings", "users"],
  "admin": {
    "username": "radha-admin",
    "email": "admin@radha.example",
    "password": "admin1234"
  }
}
```

This creates the PostgreSQL schema, stores the domain mapping, and creates the tenant admin inside the tenant schema.

Migration bridge note: existing legacy migrations contain cross-app dependencies that require public to retain some business tables during the transition. Runtime isolation still happens through tenant schemas. A later cleanup should squash/split those legacy migrations so public contains only platform tables.

## API Modules and Endpoints

All routes are under `/api/`.

### Access Control

- `GET /access-control/modules/`
- `GET /access-control/users/`
- `GET|PUT /access-control/users/<uuid:user_id>/permissions/`
- `GET /me/permissions/`

### SaaS Admin

- `GET|POST /subscription-plans/`
- `GET|PUT /subscription-plans/<uuid:id>/`
- `GET|POST /tenants/`
- `GET|PUT /tenants/<uuid:id>/`
- `POST /tenants/<uuid:id>/provision/`
- `GET /me/tenant/`

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

### Payments

- `GET|POST /payments/`
- `GET|PUT|DELETE /payments/<int:pk>/`
- `GET /all-transaction/`

### PDF Formatter

- `GET|POST /pdf-formatters/`
- `GET|PUT|PATCH|DELETE /pdf-formatters/<int:pk>/`
- `GET /pdf-formatters/<int:pk>/html/`

### Expense

- `GET|POST /expenses/`
- `GET|PUT|DELETE /expenses/<int:pk>/`
- `GET|POST /expenses-categories/`
- `GET|PUT|DELETE /expenses-categories/<int:pk>/`

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

`catering-be.sh` does:

1. Activate venv (if present)
2. Install/update the subscription status cron job
3. Run migrations
4. Start Gunicorn with `radha.wsgi:application`

Default bind: `127.0.0.1:8009`

## Scheduled Subscription Status Updates

`catering-be.sh` installs/updates the daily 1:00 AM cron job automatically
whenever PM2 starts or restarts the backend. You can also install it manually:

```bash
cd /root/catering-be
chmod +x scripts/install_subscription_status_cron.sh
./scripts/install_subscription_status_cron.sh
```

Cron uses the server's timezone. Check it with:

```bash
timedatectl
```

For 1:00 AM India time, the server timezone should be `Asia/Kolkata`.

The cron job runs:

```bash
python manage.py update_subscription_statuses
```

Output is written to:

```text
/root/catering-be/logs/update_subscription_statuses.log
```

If the project is deployed somewhere else, pass `APP_DIR`:

```bash
APP_DIR=/path/to/radha-be ./scripts/install_subscription_status_cron.sh
```

To disable automatic cron installation during app startup:

```bash
AUTO_INSTALL_SUBSCRIPTION_CRON=false ./catering-be.sh
```

To test the runner without saving subscription changes:

```bash
APP_DIR=/root/catering-be scripts/update_subscription_statuses.sh --dry-run
```

## Important Notes

- `CORS_ALLOW_ALL_ORIGINS` defaults to `True` in settings; tighten this in production.
- `branchmanagement` is present but not active in installed apps and root URLs.
- README no longer references a Postman collection file because `radha.postman_collection.json` is not present in this repository.
