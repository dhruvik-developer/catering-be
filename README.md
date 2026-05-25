# Radha Backend

Radha Backend is a Django REST API for catering and event operations.  
It includes user/auth, permissions, bookings, inventory, ingredients, vendors, expenses, payments, event staff, and ground management.

For the current end-to-end project flow, module responsibilities, active API
routes, admin coverage, and inactive module notes, see
[`CURRENT_FLOW.md`](CURRENT_FLOW.md).

For frontend implementation details for change-password and forgot-password
flows, see [`docs/password-apis.md`](docs/password-apis.md).

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
|- user/                    # Auth/login, users, branch profiles, notes, business profile
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
The first tenant admin is also attached to the tenant's main branch profile. If
no branch exists yet, the backend creates a default main branch inside that
tenant schema.

Migration bridge note: existing legacy migrations contain cross-app dependencies that require public to retain some business tables during the transition. Runtime isolation still happens through tenant schemas. A later cleanup should squash/split those legacy migrations so public contains only platform tables.

## Loading Menu Data

The `load_menu` management command imports the catering menu (categories, subcategories, and items) from [`menu.json`](menu.json) into a tenant schema. It walks the `menu` object in the JSON and inserts rows into `category_category` and `item_item` under the given tenant.

### Schema mapping

For an entry like:

```json
"Welcome Drink": {
  "Mocktails": ["Sundowner", "Berrylicious Bliss"]
}
```

The command creates:

- `category_category` row: `name="Welcome Drink"`, `parent_id=NULL` (top-level category)
- `category_category` row: `name="Mocktails"`, `parent_id=<Welcome Drink id>` (subcategory)
- `item_item` rows: `name="Sundowner"`, `name="Berrylicious Bliss"` with `category_id=<Mocktails id>`

All created rows get:

- `branch_profile_id = 1` (override with `--branch-profile-id`)
- `positions` = 1-based index among siblings at the moment of insert
- `base_cost = 0`, `selection_rate = 0` on items

Lists nested at any depth (e.g. `Starter > Chinese > Mains > [...items]`) and lists placed directly under a top-level key (e.g. `Chef's Special Baked Dishes`) are both handled.

### Usage

Preview without writing:

```powershell
python manage.py load_menu --schema=bansuricatering --dry-run
```

Run the import:

```powershell
python manage.py load_menu --schema=bansuricatering
```

Optional flags:

- `--menu-file <path>` — path to a different JSON file (defaults to `<BASE_DIR>/menu.json`)
- `--branch-profile-id <n>` — `branch_profile_id` value for all created rows (default `1`)

### Idempotency

The command is safe to re-run after updating `menu.json` with missing entries — it will not duplicate existing rows:

- Categories are matched on `(name, parent)` via `get_or_create`.
- Items are matched on `(name, category)` via `get_or_create`.
- New entries in the JSON are inserted; rows that already exist are reused.

The output summary shows the split, for example:

```text
Menu loaded into 'bansuricatering'. Categories: +2 (reused 27). Items: +15 (reused 218).
```

The tenant must already be registered (`tenant_client` row) — bootstrap it via `bootstrap_saas` or the `POST /api/tenants/` endpoint first.

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
- `GET|PUT|PATCH /users/<uuid:id>/branch/`
- `GET|POST /branch-profiles/`
- `GET|PUT|PATCH|DELETE /branch-profiles/<int:id>/`
- `GET /branch-profiles/<int:id>/users/`
- `POST /change-password/` authenticated user changes own password with `current_password` and `new_password`
- `POST /change-password/<uuid:id>/` admin/manager password update for a target user; requires `current_password` when targeting yourself
- `POST /forgot-password/` request a reset token by `username`, `email`, or `identifier`
- `POST /reset-password/` set a new password with `uid`, `token`, and `new_password`
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

## Deployment Script

`catering-be.sh` does:

1. Activate venv (if present)
2. Install/update the subscription status cron job
3. Run shared and tenant schema migrations
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
- README no longer references a Postman collection file because `radha.postman_collection.json` is not present in this repository.

## Realtime Notifications (WebSocket + FCM)

The `notifications` app delivers instant alerts to staff/vendor users when an
admin assigns them work. Live clients (app open) receive a WebSocket frame
immediately; offline clients (app closed/backgrounded) receive a Firebase
Cloud Messaging push.

Trigger point: `notifications/signals.py` listens to `post_save` on
`eventstaff.EventStaffAssignment` and calls `NotificationService.notify_user`.

### Runtime topology

| Process | Started by | Port | Handles |
|---------|-----------|------|---------|
| Gunicorn | `catering-be.sh` (child) | 8009 | `/api/*` REST |
| Daphne   | `catering-be.sh` (child) | 8010 | `/ws/*` WebSockets |
| Redis    | system / Memurai service | 6379 | Channels layer + future Celery broker |

WebSockets are long-lived async connections. Gunicorn's sync worker model
can't hold them, so we run Daphne (ASGI) alongside Gunicorn (WSGI) against
the same Django code (`radha.wsgi:application` and `radha.asgi:application`
respectively).

**One PM2 entry supervises both.** `catering-be.sh` launches gunicorn and
daphne as background children, traps SIGTERM, and exits as soon as either
child dies — PM2 then restarts the whole thing together. So you keep:

```bash
pm2 start catering-be.sh --name catering-be
```

…exactly like before. No separate WebSocket process to manage.

### 1) Install Redis

Pick the one that matches your dev OS:

**Linux / macOS:**
```bash
sudo apt install -y redis-server                   # Debian/Ubuntu
sudo systemctl enable --now redis-server
# or:  brew install redis && brew services start redis
```

**Windows — Docker (recommended)** if Docker Desktop is installed:
```powershell
docker run -d --name redis -p 6379:6379 --restart unless-stopped redis:7-alpine
docker exec redis redis-cli ping     # → PONG
```

**Windows — Memurai** if you don't want Docker: download the free Developer
edition from <https://www.memurai.com/get-memurai>. The installer registers a
Windows service that starts on boot. Verify with `memurai-cli ping`.

**Windows — WSL2**:
```bash
wsl -- sudo apt install -y redis-server
wsl -- sudo service redis-server start
```
WSL2 exposes services on the host's `127.0.0.1`, so no port-forwarding needed.

**Verify from the Python venv** before you start daphne:
```powershell
python -c "import redis; print(redis.Redis(host='127.0.0.1', port=6379).ping())"
```
Must print `True`. If it raises `ConnectionRefusedError` daphne will spin in
a reconnect loop with the WS client (every WS handshake reaches the consumer
but `channel_layer.group_add` then fails — that's the canonical symptom).

**Production**: bind to `127.0.0.1` only and set `requirepass` in
`/etc/redis/redis.conf`. Update `REDIS_URL` in `.env` accordingly
(`redis://:password@127.0.0.1:6379/0`).

### 2) Firebase service-account JSON

Download from Firebase Console → ⚙ Project settings → **Service accounts** →
"Generate new private key". Drop the file at:

```
radha-be/secrets/firebase-service-account.json   # default path
```

…or set `FIREBASE_CREDENTIALS_PATH` in `.env` to a custom location. **Add
`secrets/` to `.gitignore`** — this file authenticates the backend to Google
as the project.

If the file is absent the notification system still works over WebSocket;
only push-to-closed-app is disabled.

### 3) Environment variables

Add to `.env`:

```
REDIS_URL=redis://127.0.0.1:6379/0
FIREBASE_CREDENTIALS_PATH=/abs/path/to/firebase-service-account.json
# Optional — defaults to INFO
NOTIFICATIONS_LOG_LEVEL=DEBUG
```

### 4) Migrations

`notifications` lives in `TENANT_APPS`, so each tenant schema gets its own
`notifications_notification` and `notifications_device_token` tables:

```bash
python manage.py makemigrations notifications
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant
```

### 5) Start the server

`catering-be.sh` starts BOTH gunicorn (port 8009) and daphne (port 8010) as
child processes. One PM2 entry is enough:

```bash
pm2 start catering-be.sh --name catering-be
pm2 logs catering-be   # you should see both "Starting Daphne" and "Starting Gunicorn"
```

To override the WebSocket port or scale tuning:
```bash
DAPHNE_PORT=8020 GUNICORN_TIMEOUT=120 pm2 start catering-be.sh --name catering-be
```

**Local dev** without PM2:
```bash
./catering-be.sh
```
Two processes will start in the foreground; Ctrl+C kills both cleanly.

If you ever want to scale daphne separately (e.g. dedicate it to a different
host), you can still run it alone:
```bash
daphne -b 127.0.0.1 -p 8010 --proxy-headers radha.asgi:application
```

### 6) Nginx (production)

Add inside the existing `*.<your-domain>` server block:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8010;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
}
```

### 7) Smoke test

From `python manage.py shell` inside a tenant context:

```python
from django_tenants.utils import schema_context
from django.contrib.auth import get_user_model
from notifications.services import NotificationService

with schema_context("pruthvi"):
    u = get_user_model().objects.get(username="<staff-user>")
    NotificationService.notify_user(
        u,
        notification_type="generic",
        title="Hello",
        message="From the shell.",
        data={"route": "/dashboard"},
    )
```

Expected: one row in the tenant's `notifications_notification` table; any
open WS client (Flutter app or web bell) receives a `{"type":"notification"…}`
frame instantly; any registered device token receives an FCM push.

### Files in this app

| File | Purpose |
|------|---------|
| `notifications/models.py` | `Notification` (history) + `DeviceToken` (FCM registrations) — per-tenant |
| `notifications/services.py` | `NotificationService.notify_user(...)` — the only public entry point |
| `notifications/consumers.py` | `NotificationConsumer` — channel group `t_<schema>_u_<user_id>` |
| `notifications/middleware.py` | Tenant-aware JWT auth for WebSocket upgrades |
| `notifications/fcm.py` | Firebase Admin wrapper; lazy-init; auto-disables when credentials missing |
| `notifications/signals.py` | `post_save` receiver on `EventStaffAssignment` |
| `notifications/views.py` | REST: list, unread-count, mark-read, register-device, unregister-device |
| `radha/asgi.py` | Channels `ProtocolTypeRouter` (HTTP → Django, WebSocket → consumers) |

### Channel group naming

`t_<schema_name>_u_<user_uuid>`. Including the schema name in the group makes
cross-tenant fan-out impossible even on the theoretical chance of UUID
collisions across tenants.

### FCM dispatch

Runs in a shared `ThreadPoolExecutor(max_workers=4)` from
`NotificationService` so the REST request that triggered the notification
returns immediately. Switch to Celery only when you outgrow this — single-box
throughput of ~5 notifications/sec is fine here.
