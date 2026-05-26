from rest_framework.response import Response
from rest_framework import status, generics
from radha.Utils.permissions import *
from .serializers import *
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import logging
from radha.Utils.unit_normalizer import (
    normalize_quantity_unit,
    to_number,
    to_readable_quantity_unit,
)
from item.models import RecipeIngredient
from user.branching import (
    ensure_object_in_user_branch,
    filter_branch_queryset,
    get_branch_save_kwargs,
)
from django.db.models import F, Q
import difflib

logger = logging.getLogger(__name__)

DEFAULT_ESTIMATED_PERSONS = 100


_ASSIGNED_TO_ME_TRUTHY = {"1", "true", "yes", "on", "me"}


def _wants_assigned_to_me(request):
    raw = request.query_params.get("assigned_to_me")
    if raw is None:
        return False
    return raw.strip().lower() in _ASSIGNED_TO_ME_TRUTHY


def _restrict_to_assigned_staff(queryset, request):
    # Opt-in via ?assigned_to_me=true. Works from mobile or web. The caller
    # must be linked to a Staff record via Staff.user_account, otherwise an
    # empty queryset comes back so an unauthenticated/unlinked user can't
    # accidentally see everything just by sending the flag.
    if not _wants_assigned_to_me(request):
        return queryset
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    # Vendor users see a different slice: bookings where their vendor record
    # has a non-declined EventVendorAssignment on any session. Same shape as
    # the staff filter below — admins (no assigned_to_me flag) still see
    # everything in the unfiltered view.
    if hasattr(user, "vendor_profile") and user.vendor_profile is not None:
        return queryset.filter(
            sessions__vendor_assignments__vendor__user_account=user,
            sessions__vendor_assignments__response_status__in=["pending", "accepted"],
        ).distinct()

    # Both conditions sit in the same .filter() call on purpose — Django
    # joins them onto the SAME staff_assignment row, so the result is
    # "bookings where there is at least one assignment that is BOTH mine AND
    # not declined". Once the staff member declines every assignment on a
    # booking, it drops out of their portal entirely — admins (no
    # assigned_to_me flag) still see it with the decline reason so they know
    # to reassign.
    return queryset.filter(
        sessions__staff_assignments__staff__user_account=user,
        sessions__staff_assignments__response_status__in=["pending", "accepted"],
    ).distinct()


def _safe_amount(value):
    """Parse a money-shaped value from loose JSON (string, int, float, None).
    Returns 0 for blank / non-numeric inputs instead of raising ValueError."""
    if value is None or value == "":
        return 0
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0


def _session_id_from_query(request):
    return request.query_params.get("session_id") or request.query_params.get("session")


def _session_id_from_payload(payload):
    return payload.get("session_id") or payload.get("session")


def _normalize_lookup_name(value):
    return str(value or "").strip().lower()


def _find_order_local_ingredient(session, ingredient_name):
    order_local = getattr(session, "order_local_ingredients", None) or {}
    if not isinstance(order_local, dict):
        return None, None

    target = _normalize_lookup_name(ingredient_name)
    for name, entry in order_local.items():
        local_name = str(name or "").strip()
        if not local_name:
            continue

        candidates = {_normalize_lookup_name(local_name)}
        if isinstance(entry, dict):
            for_item = str(entry.get("for_item") or "").strip()
            if for_item:
                candidates.add(_normalize_lookup_name(f"{local_name} (for {for_item})"))

        if target in candidates:
            return local_name, entry
    return None, None


def _local_ingredient_category_name(entry):
    if isinstance(entry, dict):
        return str(entry.get("category") or "").strip()
    return ""


def _vendor_info_from_assignment(assignment):
    if not assignment:
        return None
    vendor_obj = assignment.vendor
    return {
        "id": vendor_obj.id,
        "name": vendor_obj.name,
        "mobile_no": vendor_obj.mobile_no,
        "source_type": assignment.source_type,
    }


def _extract_dish_names(node):
    """Recursively collect dish names from a selected_items payload.

    Handles flat entries (`{"name": "Jeera Rice"}`), bare strings, and
    nested subcategory dicts (`{"Juice": [{"name": "Lichi Coconet"}]}`).
    Tolerates corrupted shapes where `name` itself is a dict by recursing
    into the value instead of crashing on `.strip()`.
    """
    names = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "name" and isinstance(value, str):
                names.append(value.strip())
            else:
                names.extend(_extract_dish_names(value))
    elif isinstance(node, list):
        for item in node:
            names.extend(_extract_dish_names(item))
    elif isinstance(node, str):
        stripped = node.strip()
        if stripped:
            names.append(stripped)
    return names


def _normalize_selected_items(selected_items):
    """Wrap raw string dish entries as `{"name": str}` while leaving dicts
    untouched. Idempotent so it's safe to apply multiple times, and
    preserves nested subcategory dicts like `{"Juice": [...]}` instead of
    double-wrapping them into `{"name": {"Juice": [...]}}`."""
    if not isinstance(selected_items, dict):
        return selected_items
    normalized = {}
    for key, value in selected_items.items():
        if isinstance(value, list):
            normalized[key] = [
                {"name": item} if isinstance(item, str) else item for item in value
            ]
        else:
            normalized[key] = value
    return normalized


def calculate_ingredients_required(session_obj):
    try:
        persons = int(session_obj.estimated_persons)
    except (ValueError, TypeError):
        logger.warning(
            "Session %s has non-numeric estimated_persons=%r; falling back to %d",
            getattr(session_obj, "id", "?"),
            session_obj.estimated_persons,
            DEFAULT_ESTIMATED_PERSONS,
        )
        persons = DEFAULT_ESTIMATED_PERSONS

    selected_items = session_obj.selected_items or {}
    dish_names = _extract_dish_names(selected_items)

    # Accumulate in Decimal so scale factors like 73/100 don't drift across
    # many ingredients. Converted back to float at the response boundary.
    # `category` is captured straight from the recipe's FK chain
    # (RecipeIngredient.ingredient.category) so we don't have to round-trip
    # through a separate IngridientsItem name lookup — that round-trip used to
    # drop the category when the ingredient's branch_profile didn't match the
    # booking's, leaving the UI to fall back to "Uncategorized".
    total_ingredients = defaultdict(
        lambda: {"value": Decimal("0"), "unit": "", "used_in": set(), "category": ""}
    )

    from .models import EventItemConfig

    item_configs = {
        config.item_name.strip().lower(): config
        for config in EventItemConfig.objects.filter(
            session=session_obj
        ).select_related("vendor")
    }

    stored_outsourced_items = session_obj.outsourced_items or []
    stored_outsourced_map = {
        item.get("item_name"): item.get("vendor")
        for item in stored_outsourced_items
        if isinstance(item, dict) and item.get("item_name")
    }

    in_house_dish_names = []
    outsourced_items = []
    for dish in dish_names:
        norm_dish = dish.strip().lower()
        config = item_configs.get(norm_dish)
        if config and config.is_vendor_supplied:
            # Auto-calculate quantity from persons if flag is set
            qty = None
            unit = config.unit or ""
            if config.calculated_from_persons and config.quantity:
                qty = float(Decimal(str(config.quantity)) * persons)
            elif config.quantity:
                qty = float(Decimal(str(config.quantity)))

            vendor_info = None
            if config.vendor:
                vendor_info = {
                    "id": config.vendor.id,
                    "name": config.vendor.name,
                    "mobile_no": config.vendor.mobile_no,
                }

            # Merge with custom fields stored in JSON
            saved_vendor = stored_outsourced_map.get(dish)
            if saved_vendor and isinstance(saved_vendor, dict):
                if vendor_info is None:
                    vendor_info = saved_vendor
                else:
                    for k, v in saved_vendor.items():
                        if (
                            k not in vendor_info
                            or not vendor_info[k]
                            or k not in ["id", "name"]
                        ):
                            vendor_info[k] = v

            outsourced_items.append(
                {
                    "item_name": dish,
                    "quantity": qty,
                    "unit": unit,
                    "vendor": vendor_info,
                }
            )
        else:
            in_house_dish_names.append(dish)

    # Build a case-insensitive lookup so dish names like "Khandvi" / "khandvi" /
    # " Khandvi " in selected_items all match Item.name regardless of how it was
    # cased when the recipe was created. Without this, a single keystroke
    # difference between recipe creation and order entry silently drops the
    # whole recipe from the ingredient calculation.
    norm_dish_names = {d.strip().lower() for d in in_house_dish_names if d}

    # Tolerate NULL-branch (tenant-global) items as well as items on the
    # booking's branch — otherwise recipes created outside a branch context
    # never surface for any branched order.
    booking_branch = session_obj.booking.branch_profile
    branch_filter = Q(item__branch_profile=booking_branch) | Q(
        item__branch_profile__isnull=True
    )

    recipe_qs = RecipeIngredient.objects.select_related(
        "item", "ingredient__category"
    ).filter(branch_filter)

    matched_dishes = set()
    for ri in recipe_qs:
        item_name = (ri.item.name or "").strip()
        if not item_name:
            continue
        if item_name.lower() not in norm_dish_names:
            continue
        matched_dishes.add(item_name.lower())

        ingredient_name = ri.ingredient.name.strip()
        qty = float(ri.quantity or 0)
        unit = ri.unit or ""
        base_quantity, base_unit = normalize_quantity_unit(qty, unit)
        person_count = (
            ri.person_count
            if ri.person_count and ri.person_count > 0
            else DEFAULT_ESTIMATED_PERSONS
        )
        scale_factor = Decimal(persons) / Decimal(person_count)

        total_ingredients[ingredient_name]["value"] += (
            Decimal(str(base_quantity)) * scale_factor
        )
        if base_unit:
            total_ingredients[ingredient_name]["unit"] = base_unit
        total_ingredients[ingredient_name]["used_in"].add(item_name)
        # Pull the category straight off the recipe's FK so it survives even
        # when the IngridientsItem lives on a different branch_profile than
        # the booking — the category_map below is just a fallback.
        if (
            not total_ingredients[ingredient_name]["category"]
            and ri.ingredient.category_id
            and ri.ingredient.category
        ):
            total_ingredients[ingredient_name]["category"] = (
                ri.ingredient.category.name or ""
            )

    # Surface dishes that we tried to look up but found no recipe for. Logging
    # makes the "recipe defined but ingredients don't appear" class of bug
    # debuggable from server logs alone.
    unmatched = norm_dish_names - matched_dishes
    if unmatched:
        logger.info(
            "Session %s: no recipe rows matched for dishes %s (booking branch=%s)",
            getattr(session_obj, "id", "?"),
            sorted(unmatched),
            getattr(booking_branch, "id", None),
        )

    from ListOfIngridients.models import IngridientsItem

    # To support spelling variations like Tomato/Tomata, load all items and fallback via fuzzy matching.
    # Include NULL-branch (tenant-global) ingredient items too, so recipes that
    # reference globally-defined ingredients still resolve a category instead
    # of falling back to "Uncategorized" in the UI.
    items_with_categories = IngridientsItem.objects.select_related("category").filter(
        Q(branch_profile=booking_branch) | Q(branch_profile__isnull=True)
    )
    category_map = {
        item.name.strip().lower(): item.category.name for item in items_with_categories
    }

    from stockmanagement.models import StokeItem

    # To support spelling variations, load all stock items and then fuzzy-search names.
    # Same NULL-branch tolerance as the ingredient lookup above — without it,
    # stock for tenant-global items never gets attached to recipe ingredients.
    stock_items = StokeItem.objects.filter(
        Q(branch_profile=booking_branch) | Q(branch_profile__isnull=True)
    )
    stock_map = {}
    for item in stock_items:
        readable_quantity, readable_type = to_readable_quantity_unit(
            item.quantity, item.type
        )
        stock_map[item.name.strip().lower()] = {
            "quantity": str(to_number(readable_quantity)),
            "type": readable_type,
        }

    def fuzzy_lookup(key, mapping, cutoff=0.7):
        norm = key.strip().lower()
        if norm in mapping:
            return mapping[norm]
        close = difflib.get_close_matches(norm, mapping.keys(), n=1, cutoff=cutoff)
        if close:
            return mapping[close[0]]
        return None

    # Load relational vendor assignments instead of the JSON blob
    ingredient_vendor_assignments = {
        assign.ingredient.name.strip().lower(): assign
        for assign in IngredientVendorAssignment.objects.filter(
            session=session_obj
        ).select_related("vendor", "ingredient")
    }

    final_ingredients = {}
    for ingredient, data in total_ingredients.items():
        converted_value, converted_unit = to_readable_quantity_unit(
            float(data["value"]), data["unit"]
        )
        # Prefer the category we captured directly from the recipe FK above —
        # falls back to the branch-scoped IngridientsItem name lookup only if
        # the recipe FK didn't carry one (e.g. older rows where category was
        # null, or non-recipe code paths that populate total_ingredients).
        cat = data.get("category") or ""
        if not cat:
            cat = category_map.get(ingredient.strip().lower(), "")
        if not cat:
            cat = fuzzy_lookup(ingredient, category_map, cutoff=0.6) or ""

        stock_info = stock_map.get(ingredient.strip().lower())
        if stock_info is None:
            stock_info = fuzzy_lookup(ingredient, stock_map, cutoff=0.6) or {}

        vendor_assignment = ingredient_vendor_assignments.get(
            ingredient.strip().lower()
        )
        if not vendor_assignment:
            # Fuzzy match keys just in case
            keys = list(ingredient_vendor_assignments.keys())
            close = difflib.get_close_matches(
                ingredient.strip().lower(),
                [k.strip().lower() for k in keys],
                n=1,
                cutoff=0.6,
            )
            if close:
                matched_key = keys[[k.strip().lower() for k in keys].index(close[0])]
                vendor_assignment = ingredient_vendor_assignments.get(matched_key)

        vendor_info = _vendor_info_from_assignment(vendor_assignment)

        final_ingredients[ingredient] = {
            "quantity": f"{to_number(converted_value)} {converted_unit}".strip(),
            "category": cat,
            "available_stock": stock_info.get("quantity", "0"),
            "stock_type": stock_info.get("type", ""),
            "used_in": list(data["used_in"]),
        }
        if vendor_info:
            final_ingredients[ingredient]["vendor"] = vendor_info

    common_items = IngridientsItem.objects.filter(
        Q(branch_profile=booking_branch) | Q(branch_profile__isnull=True),
        category__is_common=True,
    ).select_related("category")
    common_names = [item.name for item in common_items]
    common_stock_items = StokeItem.objects.filter(
        Q(branch_profile=booking_branch) | Q(branch_profile__isnull=True),
        name__in=common_names,
    )
    common_stock_map = {}
    for item in common_stock_items:
        readable_quantity, readable_type = to_readable_quantity_unit(
            item.quantity, item.type
        )
        common_stock_map[item.name.strip().lower()] = {
            "quantity": str(to_number(readable_quantity)),
            "type": readable_type,
        }

    for item in common_items:
        if item.name not in final_ingredients:
            key = item.name.strip().lower()
            stock_info = common_stock_map.get(key, {})

            vendor_assignment = ingredient_vendor_assignments.get(key)
            vendor_info = _vendor_info_from_assignment(vendor_assignment)

            final_ingredients[item.name] = {
                "quantity": "0",
                "category": item.category.name,
                "available_stock": stock_info.get("quantity", "0"),
                "stock_type": stock_info.get("type", ""),
                "used_in": [],
            }
            if vendor_info:
                final_ingredients[item.name]["vendor"] = vendor_info

    # Merge in order-local ingredients — entries the user added manually from
    # the View Ingredient page for dishes that have no global recipe. Stored on
    # session.order_local_ingredients; surfaced here so the frontend sees them
    # in the same `ingredients_required` shape it already renders.
    order_local = session_obj.order_local_ingredients or {}
    if isinstance(order_local, dict):
        for name, entry in order_local.items():
            if not name:
                continue
            quantity = ""
            category = ""
            for_item = ""
            if isinstance(entry, dict):
                quantity = entry.get("quantity", "") or ""
                category = entry.get("category", "") or ""
                for_item = entry.get("for_item", "") or ""
            elif isinstance(entry, str):
                quantity = entry

            if not category:
                category = category_map.get(name.strip().lower(), "") or ""

            stock_info = stock_map.get(name.strip().lower()) or {}
            vendor_assignment = ingredient_vendor_assignments.get(name.strip().lower())
            vendor_info = _vendor_info_from_assignment(vendor_assignment)

            # Avoid clobbering a global-recipe entry if the user happened to
            # pick the same name. The frontend already namespaces with
            # "(for <Dish>)" when it detects a collision, so this is a safety
            # net for edge cases.
            display_name = name
            if display_name in final_ingredients and for_item:
                display_name = f"{name} (for {for_item})"

            final_ingredients[display_name] = {
                "quantity": str(quantity),
                "category": category,
                "available_stock": stock_info.get("quantity", "0"),
                "stock_type": stock_info.get("type", ""),
                "used_in": [for_item] if for_item else [],
                "source": "order_local",
                "for_item": for_item,
            }
            if vendor_info:
                final_ingredients[display_name]["vendor"] = vendor_info

    return final_ingredients, outsourced_items


class EventBookingViewSet(generics.GenericAPIView):
    serializer_class = EventBookingSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_bookings"

    def get_queryset(self):
        qs = filter_branch_queryset(EventBooking.objects.all(), self.request)
        return _restrict_to_assigned_staff(qs, self.request)

    def post(self, request):
        sessions = request.data.get("sessions", [])

        # Process each session's selected_items and extra_service
        for session in sessions:
            # Normalize the selected_items payload for the session
            session["selected_items"] = _normalize_selected_items(
                session.get("selected_items", {})
            )

            # Calculate extra_service_amount for the session
            extra_services = session.get("extra_service", [])
            amount = sum(_safe_amount(s.get("amount")) for s in extra_services)
            session["extra_service_amount"] = str(amount)

            # Calculate waiter_service_amount for the session.
            # waiter_service can arrive as a single dict {} or a list [{}] — normalise to list.
            raw_waiter = session.get("waiter_service", [])
            waiter_services = (
                [raw_waiter]
                if isinstance(raw_waiter, dict) and raw_waiter
                else (raw_waiter if isinstance(raw_waiter, list) else [])
            )
            waiter_amount = sum(_safe_amount(s.get("amount")) for s in waiter_services)
            session["waiter_service_amount"] = str(waiter_amount)

        request.data["sessions"] = sessions

        serializer = EventBookingSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            created_by = request.user if request.user.is_authenticated else None
            serializer.save(created_by=created_by, **get_branch_save_kwargs(request))
            return Response(
                {
                    "status": True,
                    "message": "EventBooking created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "status": False,
                "message": "Something went wrong",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        EventBooking.cancel_expired_pending_bookings()
        requested_session_id = _session_id_from_query(request)
        queryset = (
            self.get_queryset()
            .prefetch_related(
                "sessions__staff_assignments__staff__role",
                "sessions__staff_assignments__role_at_event",
                "sessions__ground_requirements__ground_item__category",
            )
            .filter(status__in=["confirm", "completed"])
            .order_by("-date")
        )
        if requested_session_id:
            queryset = queryset.filter(sessions__id=requested_session_id).distinct()
        for event_booking in queryset:
            changed = False
            for session in event_booking.sessions.all():
                if session.extra_service_amount == "0" and all(
                    service.get("extra") for service in session.extra_service
                ):
                    session.extra_service_amount = str(
                        sum(
                            _safe_amount(s.get("amount")) for s in session.extra_service
                        )
                    )
                    changed = True

                # Backfill waiter_service_amount if it was stored as "0" but has entries
                if (
                    session.waiter_service_amount in (None, "0")
                    and session.waiter_service
                ):
                    raw_ws = session.waiter_service
                    ws_list = (
                        [raw_ws]
                        if isinstance(raw_ws, dict) and raw_ws
                        else (raw_ws if isinstance(raw_ws, list) else [])
                    )
                    session.waiter_service_amount = str(
                        sum(_safe_amount(s.get("amount")) for s in ws_list)
                    )
                    changed = True

                if changed:
                    session.save()

        # Context is required so the nested EventSessionSerializer knows the
        # current user — used to set `is_mine` on each assignment payload so
        # mobile can show the right Accept/Decline buttons.
        serializer = EventBookingSerializer(
            queryset, many=True, context={"request": request}
        )

        for event_data, event_obj in zip(serializer.data, queryset):
            if requested_session_id:
                event_data["sessions"] = [
                    session_data
                    for session_data in event_data.get("sessions", [])
                    if str(session_data.get("id")) == str(requested_session_id)
                ]

            sessions_by_id = {
                session.id: session for session in event_obj.sessions.all()
            }
            for session_data in event_data.get("sessions", []):
                session_obj = sessions_by_id.get(session_data.get("id"))
                if not session_obj:
                    continue
                final_ingredients, outsourced_items = calculate_ingredients_required(
                    session_obj
                )
                session_data["ingredients_required"] = final_ingredients
                session_data["outsourced_items"] = outsourced_items

        return Response(
            {
                "status": True,
                "message": "EventBooking list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class EventBookingGetViewSet(generics.GenericAPIView):
    serializer_class = EventBookingSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_bookings"

    def get_queryset(self):
        qs = filter_branch_queryset(EventBooking.objects.all(), self.request)
        return _restrict_to_assigned_staff(qs, self.request)

    def put(self, request, pk=None):
        try:
            eventbooking = self.get_queryset().get(pk=pk)
            sessions = request.data.get("sessions")

            if sessions is not None:
                # Process each session
                for session in sessions:
                    selected_items = session.get("selected_items", {})
                    extra_service = session.get("extra_service", [])

                    if extra_service:
                        session["extra_service_amount"] = str(
                            sum(_safe_amount(s.get("amount")) for s in extra_service)
                        )

                    raw_ws = session.get("waiter_service", [])
                    ws_list = (
                        [raw_ws]
                        if isinstance(raw_ws, dict) and raw_ws
                        else (raw_ws if isinstance(raw_ws, list) else [])
                    )
                    if ws_list:
                        session["waiter_service_amount"] = str(
                            sum(_safe_amount(s.get("amount")) for s in ws_list)
                        )

                    if selected_items and isinstance(selected_items, dict):
                        session["selected_items"] = _normalize_selected_items(
                            selected_items
                        )

                request.data["sessions"] = sessions

            # Partially update the instance with only provided fields
            serializer = EventBookingSerializer(
                eventbooking, data=request.data, partial=True
            )
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                return Response(
                    {
                        "status": True,
                        "message": "EventBooking updated successfully",
                        "data": serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": False,
                    "message": "Something went wrong",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except EventBooking.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "EventBooking not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )

    def get(self, request, pk=None):
        EventBooking.cancel_expired_pending_bookings()
        requested_session_id = _session_id_from_query(request)
        try:
            eventbooking = (
                self.get_queryset()
                .prefetch_related(
                    "sessions__staff_assignments__staff__role",
                    "sessions__staff_assignments__role_at_event",
                    "sessions__ground_requirements__ground_item__category",
                )
                .get(pk=pk)
            )
            # Context needed so the nested EventSessionSerializer can populate
            # `is_mine` on each assignment from `request.user`.
            serializer = EventBookingSerializer(
                eventbooking, context={"request": request}
            )

            response_data = serializer.data
            if requested_session_id:
                response_data["sessions"] = [
                    session_data
                    for session_data in response_data.get("sessions", [])
                    if str(session_data.get("id")) == str(requested_session_id)
                ]
                if not response_data["sessions"]:
                    return Response(
                        {
                            "status": False,
                            "message": "Session not found for this event booking",
                            "data": {},
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

            sessions_by_id = {
                session.id: session for session in eventbooking.sessions.all()
            }
            for session_dict in response_data.get("sessions", []):
                session_obj = sessions_by_id.get(session_dict.get("id"))
                if not session_obj:
                    continue
                final_ingredients, outsourced_items = calculate_ingredients_required(
                    session_obj
                )
                session_dict["ingredients_required"] = final_ingredients
                session_dict["outsourced_items"] = outsourced_items

            return Response(
                {
                    "status": True,
                    "message": "EventBooking retrieved successfully",
                    "data": response_data,
                },
                status=status.HTTP_200_OK,
            )

        except EventBooking.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "EventBooking not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

    def delete(self, request, pk=None):
        try:
            eventbooking = self.get_queryset().get(pk=pk)
            eventbooking.delete()
            return Response(
                {
                    "status": True,
                    "message": "EventBooking deleted successfully",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )
        except EventBooking.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "EventBooking not found",
                    "data": {},
                },
                status=status.HTTP_200_OK,
            )


# --------------------    PendingEventBookingViewSet    --------------------


class PendingEventBookingViewSet(generics.GenericAPIView):
    serializer_class = EventBookingSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_booking_reports"

    def get_queryset(self):
        qs = filter_branch_queryset(EventBooking.objects.all(), self.request)
        return _restrict_to_assigned_staff(qs, self.request)

    def get(self, request):
        EventBooking.cancel_expired_pending_bookings()
        queryset = (
            self.get_queryset()
            .prefetch_related(
                "sessions__staff_assignments__staff__role",
                "sessions__staff_assignments__role_at_event",
                "sessions__ground_requirements__ground_item__category",
            )
            .filter(status="pending")
            .order_by("-date")
        )
        serializer = EventBookingSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(
            {
                "status": True,
                "message": "EventBooking list",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


from .serializers import EventItemConfigSerializer, IngredientVendorAssignmentSerializer
from .models import EventItemConfig, IngredientVendorAssignment


class EventItemConfigViewSet(generics.ListCreateAPIView):
    queryset = EventItemConfig.objects.all()
    serializer_class = EventItemConfigSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_item_configs"

    def get_queryset(self):
        qs = super().get_queryset()
        qs = filter_branch_queryset(
            qs,
            self.request,
            field_name="session__booking__branch_profile",
        )
        session_id = _session_id_from_query(self.request)
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        session_id = _session_id_from_payload(payload)
        session = None
        if session_id:
            payload["session"] = session_id
            from .models import EventSession

            session = EventSession.objects.select_related("booking").get(id=session_id)
            ensure_object_in_user_branch(session.booking, request)
        item_name = payload.get("item_name")

        if session_id and item_name:
            existing = EventItemConfig.objects.filter(
                session_id=session_id, item_name__iexact=item_name
            ).first()
            if existing:
                serializer = self.get_serializer(existing, data=payload, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return Response(serializer.data)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EventItemConfigDetailViewSet(generics.RetrieveUpdateDestroyAPIView):
    queryset = EventItemConfig.objects.all()
    serializer_class = EventItemConfigSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_item_configs"

    def get_queryset(self):
        return filter_branch_queryset(
            super().get_queryset(),
            self.request,
            field_name="session__booking__branch_profile",
        )


class IngredientVendorAssignmentViewSet(generics.ListCreateAPIView):
    queryset = IngredientVendorAssignment.objects.all()
    serializer_class = IngredientVendorAssignmentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ingredient_vendor_assignments"

    def get_queryset(self):
        qs = super().get_queryset()
        qs = filter_branch_queryset(
            qs,
            self.request,
            field_name="session__booking__branch_profile",
        )
        session_id = _session_id_from_query(self.request)
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs

    def create(self, request, *args, **kwargs):
        payload = request.data.copy()
        ingredient_name = str(payload.get("ingredient_name") or "").strip()
        session_id = _session_id_from_payload(payload)
        session = None
        if session_id:
            payload["session"] = session_id
            from .models import EventSession

            session = EventSession.objects.select_related(
                "booking", "booking__branch_profile"
            ).get(id=session_id)
            ensure_object_in_user_branch(session.booking, request)

        # Look up ingredient by name to get its ID
        if ingredient_name:
            from ListOfIngridients.models import IngridientsCategory, IngridientsItem

            payload["ingredient_name"] = ingredient_name
            booking_branch = session.booking.branch_profile if session else None
            booking_branch_id = getattr(booking_branch, "id", None)
            ingredient_qs = IngridientsItem.objects.filter(name__iexact=ingredient_name)
            if session is not None:
                if booking_branch_id is not None:
                    ingredient_qs = ingredient_qs.filter(
                        Q(branch_profile_id=booking_branch_id)
                        | Q(branch_profile__isnull=True)
                    )
            # Prefer branch-specific match over a global (null branch_profile) one
            ingredient_obj = ingredient_qs.order_by(
                F("branch_profile").asc(nulls_last=True)
            ).first()

            if not ingredient_obj and session is not None:
                local_name, local_entry = _find_order_local_ingredient(
                    session, ingredient_name
                )
                if local_name:
                    ingredient_qs = IngridientsItem.objects.filter(
                        name__iexact=local_name
                    )
                    if booking_branch_id is not None:
                        ingredient_qs = ingredient_qs.filter(
                            Q(branch_profile_id=booking_branch_id)
                            | Q(branch_profile__isnull=True)
                        )
                    ingredient_obj = ingredient_qs.order_by(
                        F("branch_profile").asc(nulls_last=True)
                    ).first()

                    if not ingredient_obj:
                        category_name = _local_ingredient_category_name(local_entry)
                        if not category_name:
                            return Response(
                                {
                                    "error": (
                                        f"Ingredient '{ingredient_name}' is a local "
                                        "session ingredient, but it has no category "
                                        "so it cannot be saved as a master ingredient."
                                    )
                                },
                                status=400,
                            )

                        category_qs = IngridientsCategory.objects.filter(
                            name__iexact=category_name
                        )
                        if booking_branch_id is not None:
                            category_qs = category_qs.filter(
                                Q(branch_profile_id=booking_branch_id)
                                | Q(branch_profile__isnull=True)
                            )
                        category_obj = category_qs.order_by(
                            F("branch_profile").asc(nulls_last=True)
                        ).first()
                        if not category_obj:
                            category_obj = IngridientsCategory.objects.create(
                                name=category_name,
                                branch_profile=booking_branch,
                            )

                        ingredient_obj = IngridientsItem.objects.create(
                            name=local_name,
                            category=category_obj,
                            branch_profile=booking_branch,
                        )

            if not ingredient_obj:
                return Response(
                    {"error": f"Ingredient '{ingredient_name}' not found"}, status=400
                )
            payload["ingredient"] = ingredient_obj.id

        ingredient_id = payload.get("ingredient")
        if ingredient_id and session_id:
            existing = IngredientVendorAssignment.objects.filter(
                ingredient_id=ingredient_id, session_id=session_id
            ).first()
            if existing:
                serializer = self.get_serializer(existing, data=payload, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save(source_type="manual")
                return Response(serializer.data)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(source_type="manual")
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IngredientVendorAssignmentDetailViewSet(generics.RetrieveUpdateDestroyAPIView):
    queryset = IngredientVendorAssignment.objects.all()
    serializer_class = IngredientVendorAssignmentSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "ingredient_vendor_assignments"

    def get_queryset(self):
        return filter_branch_queryset(
            super().get_queryset(),
            self.request,
            field_name="session__booking__branch_profile",
        )

    def perform_update(self, serializer):
        serializer.save(source_type="manual")


from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from eventbooking.models import EventSession, SessionChecklistTick
from eventbooking.serializers import SessionChecklistTickSerializer


def _user_can_access_session_checklist(user, session):
    """Allowed callers: admins, OR staff with at least one non-declined
    staff assignment on the session, OR vendors with at least one
    non-declined vendor assignment. Vendor's `delivered` ticks go through
    this same endpoint."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    if (
        session.staff_assignments.filter(
            staff__user_account=user,
        )
        .exclude(response_status="declined")
        .exists()
    ):
        return True
    return (
        session.vendor_assignments.filter(
            vendor__user_account=user,
        )
        .exclude(response_status="declined")
        .exists()
    )


class SessionChecklistView(APIView):
    """`/event-sessions/<session_id>/checklist/`

    GET  → list of every checklist tick for the session (staff or admin).
    POST → upsert a single tick. Body: `{ item_key, action, is_done }`.
           One row per `(session, item_key, action)` triplet — the second
           POST on the same triplet flips is_done and refreshes ticked_by /
           ticked_at instead of creating a duplicate.
    """

    permission_classes = [IsAuthenticated]

    _ALLOWED_ACTIONS = {
        SessionChecklistTick.ACTION_PREPARED,
        SessionChecklistTick.ACTION_SERVED,
        SessionChecklistTick.ACTION_RECEIVED,
        SessionChecklistTick.ACTION_DELIVERED,
        SessionChecklistTick.ACTION_AVAILABLE,
        SessionChecklistTick.ACTION_REJECTED,
    }

    def _forbidden(self):
        return Response(
            {"status": False, "message": "You can't view this checklist.", "data": []},
            status=status.HTTP_403_FORBIDDEN,
        )

    def get(self, request, session_id):
        session = get_object_or_404(EventSession, pk=session_id)
        if not _user_can_access_session_checklist(request.user, session):
            return self._forbidden()
        ticks = session.checklist_ticks.select_related("ticked_by").all()
        return Response(
            {
                "status": True,
                "message": "Checklist ticks fetched.",
                "data": SessionChecklistTickSerializer(ticks, many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, session_id):
        session = get_object_or_404(EventSession, pk=session_id)
        if not _user_can_access_session_checklist(request.user, session):
            return self._forbidden()

        item_key = str(request.data.get("item_key", "")).strip()
        action_value = str(request.data.get("action", "")).strip().lower()
        is_done = bool(request.data.get("is_done", False))
        notes = str(request.data.get("notes", "")).strip()

        if not item_key:
            return Response(
                {"status": False, "message": "`item_key` is required.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if action_value not in self._ALLOWED_ACTIONS:
            return Response(
                {
                    "status": False,
                    "message": f"`action` must be one of {sorted(self._ALLOWED_ACTIONS)}.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Rejection requires a reason so the vendor knows what went wrong.
        # Other actions allow blank notes.
        if (
            action_value == SessionChecklistTick.ACTION_REJECTED
            and is_done
            and not notes
        ):
            return Response(
                {
                    "status": False,
                    "message": "A reason is required when rejecting an item.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        tick, _created = SessionChecklistTick.objects.update_or_create(
            session=session,
            item_key=item_key,
            action=action_value,
            defaults={
                "is_done": is_done,
                "ticked_by": request.user,
                "notes": notes,
            },
        )

        # Reject = notify the vendor immediately. Mark the matching
        # `received` row false so the UI doesn't show both green-received
        # and red-rejected at the same time for one item.
        if action_value == SessionChecklistTick.ACTION_REJECTED and is_done:
            SessionChecklistTick.objects.filter(
                session=session,
                item_key=item_key,
                action=SessionChecklistTick.ACTION_RECEIVED,
            ).update(is_done=False)
            _notify_vendor_of_rejection(
                session=session,
                item_key=item_key,
                reason=notes,
                rejected_by=request.user,
            )

        return Response(
            {
                "status": True,
                "message": "Checklist tick saved.",
                "data": SessionChecklistTickSerializer(tick).data,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Vendor accept / decline / dispatch
# ---------------------------------------------------------------------------

from django.utils import timezone as dj_timezone
from datetime import datetime
from eventbooking.models import EventVendorAssignment, EventVendorAssignmentResponse
from eventbooking.serializers import EventVendorAssignmentSerializer
from notifications.services import NotificationService
from notifications.models import Notification


def _resolve_vendor_for_item_key(session, item_key):
    """Map a checklist `item_key` back to the vendor that's delivering it.
    Walks every `EventVendorAssignment` on the session and uses the same
    `_item_keys_for_vendor_on_session()` helper that the dispatch flow
    uses, so the lookup is consistent with how rows were created."""
    for assignment in session.vendor_assignments.select_related(
        "vendor", "vendor__user_account"
    ):
        keys = _item_keys_for_vendor_on_session(session, assignment.vendor)
        if item_key in keys:
            return assignment.vendor
    return None


def _notify_vendor_of_rejection(session, item_key, reason, rejected_by):
    """Push a notification to the vendor when the receiver rejects an item
    they delivered. The vendor's mobile app gets a foreground WS frame
    (live) AND an FCM push (offline). Falls through silently if the item
    can't be mapped back to a vendor user — we never want a notification
    failure to block the staff member's reject action."""
    try:
        vendor = _resolve_vendor_for_item_key(session, item_key)
        if vendor is None or vendor.user_account is None:
            return
        # Pretty label: drop the prefix so the message reads naturally.
        if ":" in item_key:
            label = item_key.split(":", 1)[1]
            if "::" in label:
                label = label.split("::", 1)[0]
        else:
            label = item_key

        booking = getattr(session, "booking", None)
        booking_name = getattr(booking, "name", "") if booking else ""
        booking_id = getattr(booking, "id", None) if booking else None
        rejected_by_name = (
            rejected_by.get_full_name() or rejected_by.username
            if rejected_by and rejected_by.is_authenticated
            else "Staff"
        )

        NotificationService.notify_user(
            vendor.user_account,
            notification_type=Notification.TYPE_VENDOR_RESPONSE,
            title=f"Item rejected: {label}",
            message=(
                f"{rejected_by_name} rejected '{label}'"
                + (f" for {booking_name}" if booking_name else "")
                + (f". Reason: {reason}" if reason else ".")
            ),
            data={
                "route": "/vendor/session-detail",
                "booking_id": booking_id,
                "session_id": session.id,
                "item_key": item_key,
                "reason": reason,
            },
        )
    except Exception:
        logger.exception(
            "Failed to notify vendor about rejection of %s on session %s",
            item_key,
            getattr(session, "id", None),
        )
from notifications.models import Notification
from notifications.services import NotificationService, iter_admin_recipients


def _notify_admins_of_vendor_response(assignment, response_value, reason, item_key):
    """Fan a vendor accept/decline out to every catering admin. Per-item
    responses (item_key set) are still surfaced because the admin still
    benefits from seeing "Vendor X declined Pizza for Session 2" — the body
    just calls out the item so the admin doesn't think the whole session
    was rejected."""
    vendor = assignment.vendor
    session = assignment.session
    booking = getattr(session, "booking", None) if session else None
    vendor_name = getattr(vendor, "name", None) or "A vendor"
    branch_id = getattr(vendor, "branch_profile_id", None)

    accepted = response_value == "accepted"
    scope = f" for '{item_key}'" if item_key else ""
    booking_label = booking.name if booking else "an event"

    if accepted:
        title = "Vendor accepted assignment"
        message = f"{vendor_name} accepted{scope} on {booking_label}."
    else:
        title = "Vendor declined assignment"
        base = f"{vendor_name} declined{scope} on {booking_label}."
        message = f"{base} Reason: {reason}" if reason else base

    data_payload = {
        "route": f"/view-order-details/{booking.id}" if booking else "",
        "event_id": booking.id if booking else None,
        "session_id": session.id if session else None,
        "assignment_id": assignment.id,
        "response": response_value,
        "reason": reason or "",
        "item_key": item_key or "",
        "vendor_id": getattr(vendor, "id", None),
        "vendor_name": vendor_name,
    }
    for admin in iter_admin_recipients(branch_id):
        NotificationService.notify_user(
            admin,
            notification_type=Notification.TYPE_VENDOR_RESPONSE,
            title=title,
            message=message,
            data=data_payload,
        )


def _parse_iso_datetime(value):
    """Accept ISO-8601 strings (with or without trailing Z), epoch seconds,
    or `None`. Returns a timezone-aware datetime or None. Tolerant on purpose
    — mobile clients send a variety of shapes depending on platform."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return dj_timezone.make_aware(datetime.fromtimestamp(float(value)))
        except (ValueError, OSError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dj_timezone.is_naive(parsed):
            parsed = dj_timezone.make_aware(parsed)
        return parsed
    return None


class _VendorAssignmentBaseView(APIView):
    """Shared lookup logic — pulls an `EventVendorAssignment` by id and
    verifies the request.user owns the vendor it points at. Anything else
    returns 403 so a vendor can't respond on behalf of another vendor."""

    permission_classes = [IsAuthenticated]

    def _get_assignment_for_user(self, pk, user):
        try:
            assignment = EventVendorAssignment.objects.select_related(
                "vendor", "vendor__user_account", "session", "session__booking"
            ).get(pk=pk)
        except EventVendorAssignment.DoesNotExist:
            return None, Response(
                {"status": False, "message": "Vendor assignment not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_admin = getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
        vendor_user_id = getattr(assignment.vendor, "user_account_id", None)
        if not is_admin and vendor_user_id != user.id:
            return None, Response(
                {"status": False, "message": "Not your assignment.", "data": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return assignment, None


class VendorAssignmentRespondView(_VendorAssignmentBaseView):
    """`POST /event-vendor-assignments/<id>/respond/`

    Body (session-level):  `{ "response": "accepted"|"declined", "reason": "..." }`
    Body (per-item):       `{ "response": "accepted"|"declined", "item_key": "...", "reason": "..." }`

    For per-item declines, the assignment's overall response_status is NOT
    flipped — partial decline is stored in `declined_item_keys` so the
    vendor can still accept the rest of the session. A history row is
    appended either way."""

    def post(self, request, pk):
        assignment, error = self._get_assignment_for_user(pk, request.user)
        if error is not None:
            return error

        response_value = str(request.data.get("response", "")).strip().lower()
        item_key = str(request.data.get("item_key", "")).strip()
        reason = str(request.data.get("reason", "")).strip()

        if response_value not in {"accepted", "declined"}:
            return Response(
                {
                    "status": False,
                    "message": "`response` must be 'accepted' or 'declined'.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if response_value == "declined" and not reason:
            return Response(
                {
                    "status": False,
                    "message": "A reason is required when declining.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = dj_timezone.now()
        if item_key:
            # Per-item: update `declined_item_keys` only. Session-level
            # response_status is left alone — see docstring above.
            declined = list(assignment.declined_item_keys or [])
            if response_value == "declined":
                if item_key not in declined:
                    declined.append(item_key)
            else:
                declined = [k for k in declined if k != item_key]
            assignment.declined_item_keys = declined
            assignment.save(update_fields=["declined_item_keys", "updated_at"])
        else:
            # Session-level: flip response_status. Clear decline_reason on
            # accept so a previously-declined-then-re-accepted row reads
            # clean for admins.
            assignment.response_status = response_value
            assignment.decline_reason = reason if response_value == "declined" else ""
            assignment.responded_at = now
            assignment.save(
                update_fields=[
                    "response_status",
                    "decline_reason",
                    "responded_at",
                    "updated_at",
                ]
            )

        EventVendorAssignmentResponse.objects.create(
            assignment=assignment,
            item_key=item_key,
            response=response_value,
            reason=reason,
            responded_by=request.user if request.user.is_authenticated else None,
            responded_at=now,
        )

        # Alert the catering admins so vendor responses surface in the bell.
        # Best-effort — a failure here must not break the vendor's response.
        try:
            _notify_admins_of_vendor_response(
                assignment, response_value, reason, item_key
            )
        except Exception:  # noqa: BLE001 — notification is best-effort
            logger.exception(
                "Failed to dispatch vendor-response admin notification "
                "(assignment=%s)",
                assignment.id,
            )

        return Response(
            {
                "status": True,
                "message": (
                    "Per-item response saved." if item_key else "Response saved."
                ),
                "data": EventVendorAssignmentSerializer(assignment).data,
            },
            status=status.HTTP_200_OK,
        )


def _item_keys_for_vendor_on_session(session, vendor):
    """Compute the `SessionChecklistTick.item_key`s that belong to this
    vendor on this session. Mirrors the keys the Flutter UI generates:
        ingredient:<ingredient_name>            (raw ingredients)
        outsourced:<item_name>::<vendor_name>   (outsourced dishes)

    Used by the dispatch endpoint to auto-tick `delivered` for every item
    the vendor is bringing — so the staff/receiver screen flips the per-row
    "Dispatched" chip to green without the vendor having to tick each one
    by hand."""
    keys = []
    vendor_name_norm = (vendor.name or "").strip().lower()

    # `assigned_vendors`: { ingredient_name: { id, name, mobile_no, ... } }
    assigned = getattr(session, "assigned_vendors", None) or {}
    if isinstance(assigned, dict):
        for ingredient_name, vend in assigned.items():
            if not isinstance(vend, dict):
                continue
            raw_id = vend.get("id") or vend.get("vendor_id")
            try:
                vid = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                vid = None
            matches_by_id = vid == vendor.id if vid is not None else False
            matches_by_name = (
                str(vend.get("name") or vend.get("vendor_name") or "").strip().lower()
                == vendor_name_norm
            )
            if matches_by_id or matches_by_name:
                keys.append(f"ingredient:{ingredient_name}")

    # `outsourced_items`: [ { item_name, vendor: {id, name, ...}, ... } ]
    outsourced = getattr(session, "outsourced_items", None) or []
    if isinstance(outsourced, list):
        for item in outsourced:
            if not isinstance(item, dict):
                continue
            vend = item.get("vendor") if isinstance(item.get("vendor"), dict) else None
            raw_id = (vend or {}).get("id") or (vend or {}).get("vendor_id")
            try:
                vid = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                vid = None
            vname = ""
            if vend:
                vname = str(vend.get("name") or vend.get("vendor_name") or "").strip()
            if not vname:
                vname = str(item.get("vendor_name") or "").strip()
            matches_by_id = vid == vendor.id if vid is not None else False
            matches_by_name = vname.lower() == vendor_name_norm
            if matches_by_id or matches_by_name:
                item_name = str(
                    item.get("item_name") or item.get("name") or ""
                ).strip()
                if item_name:
                    # Use the vendor's canonical name (not whatever shape is
                    # in the JSON) so the key matches what the Flutter UI
                    # generates from the same source on the receiver side.
                    keys.append(f"outsourced:{item_name}::{vendor.name}")

    return keys


class VendorAssignmentDispatchView(_VendorAssignmentBaseView):
    """`POST /event-vendor-assignments/<id>/dispatch/`

    Body: `{ "driver_name": "...", "driver_phone": "...", "driver_eta": "..." }`

    Saves the driver/dispatch details, stamps `dispatched_at`, AND
    auto-creates `SessionChecklistTick(action='delivered', is_done=True)`
    rows for every item this vendor is bringing — that's what flips the
    per-row "Dispatched" chip on the staff/receiver screen. Items the
    vendor declined per-item are intentionally skipped (no truck is
    coming for those)."""

    def post(self, request, pk):
        assignment, error = self._get_assignment_for_user(pk, request.user)
        if error is not None:
            return error

        if assignment.response_status == EventVendorAssignment.RESPONSE_DECLINED:
            return Response(
                {
                    "status": False,
                    "message": "Cannot dispatch a declined assignment.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        driver_name = str(request.data.get("driver_name", "")).strip()
        driver_phone = str(request.data.get("driver_phone", "")).strip()
        eta = _parse_iso_datetime(request.data.get("driver_eta"))

        if not driver_name or not driver_phone:
            return Response(
                {
                    "status": False,
                    "message": "Driver name and phone are required.",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment.driver_name = driver_name
        assignment.driver_phone = driver_phone
        assignment.driver_eta = eta
        assignment.dispatched_at = dj_timezone.now()
        assignment.save(
            update_fields=[
                "driver_name",
                "driver_phone",
                "driver_eta",
                "dispatched_at",
                "updated_at",
            ]
        )

        # Auto-tick `delivered` for every item this vendor is bringing so
        # the staff screen reflects the dispatch state without the vendor
        # having to tap each row. Per-item-declined keys are excluded.
        declined = set(assignment.declined_item_keys or [])
        item_keys = [
            k
            for k in _item_keys_for_vendor_on_session(
                assignment.session, assignment.vendor
            )
            if k not in declined
        ]
        for key in item_keys:
            SessionChecklistTick.objects.update_or_create(
                session=assignment.session,
                item_key=key,
                action=SessionChecklistTick.ACTION_DELIVERED,
                defaults={"is_done": True, "ticked_by": request.user},
            )

        return Response(
            {
                "status": True,
                "message": "Dispatch details saved.",
                "data": EventVendorAssignmentSerializer(assignment).data,
            },
            status=status.HTTP_200_OK,
        )


class MyVendorAssignmentsView(APIView):
    """`GET /event-vendor-assignments/mine/` — flat list of every vendor
    assignment for the logged-in vendor user. Lets the mobile app render the
    "To accept / Today / Upcoming" cards without flattening sessions on the
    client. Admins get an empty list here on purpose; they have the full
    bookings list view for the same data."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not (hasattr(user, "vendor_profile") and user.vendor_profile is not None):
            return Response(
                {"status": True, "message": "Not a vendor user.", "data": []},
                status=status.HTTP_200_OK,
            )
        assignments = (
            EventVendorAssignment.objects.select_related(
                "session",
                "session__booking",
                "vendor",
            )
            .filter(vendor__user_account=user)
            .order_by("session__event_date", "session__event_time")
        )
        return Response(
            {
                "status": True,
                "message": "Vendor assignments fetched.",
                "data": EventVendorAssignmentSerializer(assignments, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class VendorReceiveAllView(APIView):
    """`POST /event-sessions/<session_id>/vendor-receive/<vendor_id>/`

    Bulk-marks every item belonging to one vendor on the session as
    received (`SessionChecklistTick(action='received', is_done=True)`).
    Items the vendor declined per-item, or that the receiver already
    rejected, are intentionally skipped.

    Receiver-side action — only staff/admin can call this (vendor users
    can't mark their own delivery as received). Returns the list of
    item_keys that were touched so the client can update its local state
    without a follow-up GET."""

    permission_classes = [IsAuthenticated]

    def post(self, request, session_id, vendor_id):
        user = request.user
        is_admin = getattr(user, "is_staff", False) or getattr(
            user, "is_superuser", False
        )
        is_vendor = (
            hasattr(user, "vendor_profile") and user.vendor_profile is not None
        )
        if is_vendor and not is_admin:
            return Response(
                {
                    "status": False,
                    "message": "Vendors can't mark their own delivery as received.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        session = get_object_or_404(EventSession, pk=session_id)
        if not _user_can_access_session_checklist(user, session):
            return Response(
                {
                    "status": False,
                    "message": "You can't update this checklist.",
                    "data": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            assignment = EventVendorAssignment.objects.select_related(
                "vendor"
            ).get(session_id=session_id, vendor_id=vendor_id)
        except EventVendorAssignment.DoesNotExist:
            return Response(
                {
                    "status": False,
                    "message": "Vendor is not assigned to this session.",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        declined = set(assignment.declined_item_keys or [])
        # Skip anything the receiver already flagged as rejected — they
        # should change the rejected row first if they meant to accept it.
        rejected_keys = set(
            SessionChecklistTick.objects.filter(
                session_id=session_id,
                action=SessionChecklistTick.ACTION_REJECTED,
                is_done=True,
            ).values_list("item_key", flat=True)
        )

        keys = [
            k
            for k in _item_keys_for_vendor_on_session(session, assignment.vendor)
            if k not in declined and k not in rejected_keys
        ]

        for key in keys:
            SessionChecklistTick.objects.update_or_create(
                session=session,
                item_key=key,
                action=SessionChecklistTick.ACTION_RECEIVED,
                defaults={"is_done": True, "ticked_by": user},
            )

        return Response(
            {
                "status": True,
                "message": f"Marked {len(keys)} item(s) received.",
                "data": {"item_keys": keys},
            },
            status=status.HTTP_200_OK,
        )
