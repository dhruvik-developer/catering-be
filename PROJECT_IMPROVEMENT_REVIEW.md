# Project Improvement Review — radha-be

**Scope:** Full audit of Django + DRF backend for catering/event management.
**Date:** 2026-04-24
**Apps audited:** `accesscontrol`, `category`, `item`, `vendor`, `eventbooking`, `eventstaff`, `groundmanagement`, `stockmanagement`, `Expense`, `payments`, `user`, `ListOfIngridients`.

---

## 🎯 Top 5 Priority Fixes

If only 5 things get done, do these:

| # | Issue | File | Impact |
|---|---|---|---|
| 1 | Payment model uses `decimal_places=0` — paise are lost | `payments/models.py:28-40` | Data correctness |
| 2 | Error responses return HTTP 200 | Multiple — see Critical #2 | API contract broken |
| 3 | No pagination on list endpoints | Multiple — see High #6 | OOM / slow responses at scale |
| 4 | Missing `created_by` on `Expense`, `Payment`, `StokeItem` | Multiple — see Critical #3 | No audit trail |
| 5 | N+1 query in ingredient calculation | `eventbooking/views.py:208-209` | Performance |

---

## 🔴 Critical

### 1. Payment model stores amounts with `decimal_places=0`

**File:** `payments/models.py:28-40`

```python
total_amount = models.DecimalField(max_digits=100, decimal_places=0)
total_extra_amount = models.DecimalField(max_digits=250, decimal_places=0)
advance_amount = models.DecimalField(max_digits=100, decimal_places=0)
pending_amount = models.DecimalField(max_digits=100, decimal_places=0, null=True, blank=True)
transaction_amount = models.DecimalField(max_digits=100, decimal_places=0)
settlement_amount = models.DecimalField(max_digits=100, decimal_places=0, null=True, blank=True)
```

**Why it matters:** `decimal_places=0` means ₹1500.50 rounds to ₹1501. Currency values *must* store paise. Also `max_digits=100`/`250` is absurd — allows numbers up to 10^100 (universe has ~10^80 atoms). Indexing and storage overhead for nothing.

**Fix:** Change all amount fields to `DecimalField(max_digits=12, decimal_places=2)` (supports up to ₹9,999,999,999.99). Requires migration + data backfill if existing rows have truncated paise.

---

### 2. Error responses return `HTTP 200`

**Files:** `eventbooking/views.py:351`, `stockmanagement/views.py:40,111,134`, `payments/views.py:181`, many others.

**Example:**
```python
return Response(
    {"status": False, "message": "Something went wrong", "data": {}},
    status=status.HTTP_200_OK,  # ❌ Should be 400 or 500
)
```

**Why it matters:** HTTP clients use status codes to decide whether a request succeeded. Returning 200 for validation failures breaks error handling in the frontend, retry logic, monitoring alerts, and standard HTTP tooling (curl, Postman, etc.).

**Fix:** Use the right codes:
- `400 Bad Request` — validation errors, malformed input
- `404 Not Found` — resource doesn't exist
- `409 Conflict` — duplicate / state conflict
- `500 Internal Server Error` — unexpected errors (or let DRF handle)

---

### 3. Missing `created_by` / `updated_by` on critical models

**Files:** `Expense/models.py`, `payments/models.py`, `stockmanagement/models.py`

**Why it matters:** EventBooking now tracks its creator (just fixed). But **Expense, Payment, StokeItem** still have no audit trail. If ₹50,000 suddenly disappears from stock, there's no way to find who adjusted it. Critical for any business handling money or inventory.

**Fix:** Apply the same pattern used for `EventBooking`:

```python
created_by = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name="created_<model_name>s",
)
```

Update the corresponding view POST to pass `created_by=request.user`, and expose `created_by` + `created_by_username` as read-only fields in the serializer.

**Models that need this:**
- `Expense` — expense entries
- `Payment` — payment records
- `TransactionHistory` — individual transactions
- `StokeItem` + add/remove stock operations

---

### 4. `SECRET_KEY` has an insecure fallback

**File:** `radha/settings.py:52`

```python
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
```

**Why it matters:** If `DJANGO_SECRET_KEY` is missing in production (forgotten `.env`), Django silently falls back to a well-known insecure value. This key signs session cookies, CSRF tokens, JWT signatures, password reset links. An attacker with the key can forge any of these.

**Fix:**
```python
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production")
    SECRET_KEY = "django-insecure-dev-only"  # dev fallback, never used in prod
```

---

### 5. Stock adjustment endpoint may have weak permission check (VERIFY BEFORE FIXING)

**File:** `stockmanagement/views.py:317`

**Claim (needs verification):** `AddRemoveStokeItemViewSet` uses `IsOwnerOrAdmin` permission, but `StokeItem` has no `user` field — so the ownership check may silently pass for any authenticated user.

**Why it matters:** If true, any authenticated user (even a vendor with a login account) could increase or decrease stock, potentially covering theft or causing production errors.

**Fix:** First test the actual behavior by calling the endpoint as a non-admin user. If confirmed, change permission to `IsAdminUser` or implement a custom `IsStockManager` permission class.

---

## 🟠 High

### 6. No pagination on list endpoints

**Files:** `eventbooking/views.py:354-420`, `payments/views.py:20-30`, `stockmanagement/views.py:62-72`, `Expense/views.py:17-23`, most list views.

**Why it matters:** Endpoints like `GET /api/event-bookings/` return `.all()` with no limit. With thousands of bookings, this causes:
- High memory usage on the server
- Multi-second response times
- Browser/network timeouts on the client
- Wasted bandwidth

**Fix:** Add to `settings.py`:
```python
REST_FRAMEWORK = {
    ...
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
```
Then use `ListAPIView` / `ListModelMixin` instead of custom `get()` methods, or manually paginate.

---

### 7. N+1 query in ingredient calculation

**File:** `eventbooking/views.py:208-209`

```python
"source_type": IngredientVendorAssignment.objects.filter(
    session=session_obj, ingredient__name__iexact=ingredient
).first().source_type if IngredientVendorAssignment.objects.filter(...).exists() else "manual"
```

This query runs **inside a loop** over ingredients. Two queries per ingredient (`.exists()` + `.first()`). For 100 ingredients = 200 queries per request.

**Fix:** Fetch once upfront:
```python
assignments = {
    a.ingredient.name.lower(): a
    for a in IngredientVendorAssignment.objects
        .filter(session=session_obj)
        .select_related("vendor", "ingredient")
}
# Then inside the loop:
source_type = assignments.get(ingredient.lower()).source_type if ingredient.lower() in assignments else "manual"
```

---

### 8. Inconsistent response envelope

**Example comparison:**

`eventbooking/views.py:337-344`:
```python
return Response({"status": True, "message": "...", "data": serializer.data}, status=...)
```

`vendor/views.py:90-91` (after cleanup):
```python
return Response({"status": True, "message": "...", "data": serializer.data})
```

Some endpoints add `HTTP_200_OK` explicitly, some omit it. Some wrap in `status/message/data`, some return raw DRF responses. Pagination responses add yet another shape (`{count, next, previous, results}`).

**Fix:** Define one canonical envelope:
- Use a DRF custom exception handler for errors
- Use a mixin or renderer for success envelope
- Document the contract in a central place

---

### 9. Missing DB indexes on frequently-filtered fields

**Files:** Multiple models.

Fields queried in filters but not indexed:
- `EventBooking.status` — `.filter(status="pending")` scans full table
- `Expense.category`, `Expense.entity` — common filters
- `Payment.booking` — FK but may not have index depending on Django version
- `StokeItem.category` — filtered by category
- `EventBooking.date` — used for date-range queries and ordering

**Fix:** Add to each model's `Meta`:
```python
class Meta:
    indexes = [
        models.Index(fields=["status"]),
        models.Index(fields=["-date"]),
    ]
```

---

### 10. Cascade-delete risk on EventBooking

**File:** `eventbooking/models.py:83-84`

```python
class EventSession(models.Model):
    booking = models.ForeignKey(EventBooking, on_delete=models.CASCADE, ...)
```

Deleting an `EventBooking` silently deletes all sessions, staff assignments, payments, ground requirements, etc. No confirmation, no recovery.

**Why it matters:** A fat-finger delete (e.g., via admin panel) loses months of business data.

**Fix options (pick one):**
1. **Soft delete:** Add `deleted_at` field; use `SoftDeleteManager` so deleted rows are hidden but recoverable.
2. **`on_delete=PROTECT`:** Prevent deletion if related sessions exist; require explicit cascade.
3. **Admin restriction:** Disable `has_delete_permission` for non-superusers in Django admin.

---

## 🟡 Medium

### 11. Zero test coverage on 9 of 13 apps

Only `eventstaff/tests.py`, `vendor/tests.py`, `user/tests.py`, `accesscontrol/tests.py` have meaningful tests. The rest are 3-line stubs.

**Why it matters:** Every change risks silent regression. Payment calculation, booking state machine, stock adjustment — none verified.

**Fix priority:** Start with critical flows —
1. `EventBooking` creation + update
2. `Payment` status calculation
3. `StokeItem` add/remove
4. `EventStaffAssignment` payment summary

Use `pytest-django` + `factory_boy` for cleaner test data setup.

---

### 12. Star imports hide dependencies

**Files:** Most `urls.py` files: `from .views import *`; some serializers: `from .models import *`.

**Why it matters:** When a view is deleted, broken imports don't surface until runtime. IDEs can't track usage. Refactoring is dangerous.

**Fix:** Explicit imports:
```python
from .views import EventBookingViewSet, EventBookingGetViewSet, PendingEventBookingViewSet
```

---

### 13. Long view methods mixing concerns

**File:** `eventstaff/views.py:144-261` — `fixed_payment_summary` is 117 lines.
**File:** `eventbooking/views.py:301-420` — `EventBookingViewSet.get` is 66 lines with filtering + business logic + serialization.

**Why it matters:** Testing is impossible when business logic is welded to HTTP handling.

**Fix:** Extract pure functions:
```python
# eventstaff/services.py
def calculate_fixed_payment_summary(staff) -> dict:
    ...

# eventstaff/views.py
def fixed_payment_summary(self, request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    summary = calculate_fixed_payment_summary(staff)
    return Response({"status": True, "data": summary})
```

---

### 14. Missing default ordering on list models

Models without `class Meta: ordering` return unpredictable row order on list endpoints. With pagination, this causes duplicate/missing rows across pages.

**Affected:** Check `IngridientsItem`, `Category`, `StokeItem`, a few others.

**Fix:**
```python
class Meta:
    ordering = ["-created_at"]  # or ["name"]
```

---

### 15. Naming inconsistency: "Stoke" vs "Stock", "Ingridients" vs "Ingredients"

**Files:** `stockmanagement/models.py` uses `StokeItem`, `StokeCategory`; app `ListOfIngridients` misspells "Ingredients".

**Why it matters:** New developers confused; API endpoints reveal typos to clients.

**⚠️ Don't fix lightly.** The frontend is already deployed using these names. A rename means:
- Model migration (table renames)
- Data migration (preserve rows)
- URL rename
- Frontend coordination
- Possible downtime window

**Recommendation:** Defer until a major version bump. Or introduce new names alongside old ones and deprecate old in next release.

---

### 16. Inconsistent `permission_resource` naming

Compare:
- `eventbooking/views.py:304` → `"event_bookings"` (snake_case plural)
- `eventstaff/views.py:39` → `"staff_roles"` (snake_case plural)
- `payments/views.py:18` → `"payments"` (no prefix)
- Some views omit `permission_resource` entirely.

**Why it matters:** `sync_permissions` command builds catalog from these values. Inconsistency leads to duplicate permissions, missing ones, hard-to-audit access control.

**Fix:** Define a convention (e.g., `{app}_{resource_plural}`) and enforce via code review or a lint check.

---

### 17. `EventSession.save()` / `EventStaffAssignment.save()` do heavy work

**File:** `eventstaff/models.py:264-296`

`payment_status` is recalculated on every save from `paid_amount` vs `remaining_amount`. Brittle — direct ORM `.update()` bypasses save(), so status can become stale.

**Fix:** Use a `@property` or recompute via manager method. Don't rely on `save()` side-effects for derived state.

---

## 🟢 Low / Nice-to-have

### 18. `EventItemConfig.item_name` is a `CharField` instead of FK to `Item`

**File:** `eventbooking/models.py:133`

Storing the item name as a string means:
- Renaming an `Item` doesn't propagate
- No referential integrity
- Can't JOIN for reporting

**Fix:** Migrate to `item = ForeignKey(Item, on_delete=PROTECT)` with a data migration mapping names → FKs.

---

### 19. `settings.py` not split by environment

One monolithic `settings.py` mixes dev and prod. Easy to accidentally commit `DEBUG=True`.

**Fix:**
```
radha/
  settings/
    __init__.py
    base.py
    dev.py
    prod.py
```

Set `DJANGO_SETTINGS_MODULE` per environment.

---

### 20. No structured logging

Critical flows (booking creation, payment, stock adjustment) have no `logger.info(...)` calls. Debugging production requires reading DB directly.

**Fix:** Add module-level logger:
```python
import logging
logger = logging.getLogger(__name__)
# ...
logger.info("EventBooking created", extra={"booking_id": booking.id, "user": request.user.id})
```

Configure `LOGGING` in settings.py with file + structured format.

---

### 21. Phone number validation is weak

**Files:** `EventBooking.mobile_no` = `CharField(max_length=17)`, `Vendor.mobile_no` = `CharField(max_length=15)`.

Accepts anything: "abc", "12", "!!!!!".

**Fix:** Use `django-phonenumber-field` or at minimum a `RegexValidator(r'^\+?\d{10,15}$')`.

---

### 22. `CORS_ALLOW_METHODS = ["*"]`

**File:** `radha/settings.py:67-68`

Wildcard allows DELETE, PATCH from any whitelisted origin. Per defense-in-depth, be explicit.

**Fix:**
```python
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
```

---

### 23. Unused `rule = BooleanField(default=False)` on multiple models

**Files:** `EventBooking.rule`, `Payment.rule`, more.

The field exists but is never read/set in any business logic. Dead column.

**Fix:** Either document the intent with a comment explaining when it will be used, or remove via migration.

---

### 24. Missing docstrings on complex functions

**Examples:** `calculate_ingredients_required()` (eventbooking/views.py:41), `_safe_amount()` (eventbooking/views.py:22).

**Fix:** One-line docstring each — no essays, just the signature and what it returns.

---

### 25. Redundant Decimal↔float conversions in payment calc

**File:** `eventstaff/views.py:183-187`

Values are wrapped in `Decimal(...)` then converted via `float(...)` then quantized. Precision is lost and regained pointlessly.

**Fix:** Stay in `Decimal` throughout. Only convert to `float`/`str` at the response boundary.

---

## Action Plan (suggested order)

### Sprint 1 — Data correctness & contracts (1-2 days)
- [ ] Fix Payment model decimal fields + migration
- [ ] Fix HTTP status codes across all views
- [ ] Add `SECRET_KEY` validation in settings
- [ ] Verify and fix stock adjustment permission (after manual test)

### Sprint 2 — Audit trail (1 day)
- [ ] Add `created_by` to Expense, Payment, TransactionHistory, StokeItem
- [ ] Update corresponding views + serializers
- [ ] Single migration, single commit

### Sprint 3 — Scaling & performance (1-2 days)
- [ ] Add DRF pagination globally
- [ ] Fix N+1 in `calculate_ingredients_required`
- [ ] Add DB indexes on filter fields
- [ ] Add `Meta.ordering` where missing

### Sprint 4 — Robustness (2-3 days)
- [ ] Write tests for critical flows (booking, payment, stock)
- [ ] Refactor long view methods into services
- [ ] Replace star imports with explicit
- [ ] Add structured logging

### Sprint 5 — Quality of life (ongoing)
- [ ] Split settings.py
- [ ] Phone number validation
- [ ] CORS method whitelist
- [ ] Remove `rule` dead field
- [ ] Docstrings on complex functions

---

## What to defer

- **Rename Stoke → Stock, Ingridients → Ingredients** — breaks frontend contract, defer to major version.
- **`EventItemConfig.item_name` → FK migration** — needs data migration + frontend coordination; low impact if names are stable.
- **Settings.py split** — nice but not urgent if single-server deployment.

---

*This review was generated based on static analysis of the codebase as of 2026-04-24.  Some findings (especially #5 permission claim) should be verified with runtime testing before fixing.*
