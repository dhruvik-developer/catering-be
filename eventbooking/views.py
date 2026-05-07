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
import difflib


logger = logging.getLogger(__name__)

DEFAULT_ESTIMATED_PERSONS = 100


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
    dish_names = []

    if isinstance(selected_items, dict):
        for category_items in selected_items.values():
            if isinstance(category_items, list):
                for item in category_items:
                    if isinstance(item, dict) and item.get("name"):
                        dish_names.append(item["name"].strip())
                    elif isinstance(item, str):
                        dish_names.append(item.strip())
    elif isinstance(selected_items, list):
        for item in selected_items:
            if isinstance(item, dict) and item.get("name"):
                dish_names.append(item["name"].strip())
            elif isinstance(item, str):
                dish_names.append(item.strip())

    # Accumulate in Decimal so scale factors like 73/100 don't drift across
    # many ingredients. Converted back to float at the response boundary.
    total_ingredients = defaultdict(lambda: {"value": Decimal("0"), "unit": "", "used_in": set()})

    from .models import EventItemConfig

    item_configs = {
        config.item_name.strip().lower(): config 
        for config in EventItemConfig.objects.filter(session=session_obj).select_related("vendor")
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
                    "mobile_no": config.vendor.mobile_no
                }
            
            # Merge with custom fields stored in JSON
            saved_vendor = stored_outsourced_map.get(dish)
            if saved_vendor and isinstance(saved_vendor, dict):
                if vendor_info is None:
                    vendor_info = saved_vendor
                else:
                    for k, v in saved_vendor.items():
                        if k not in vendor_info or not vendor_info[k] or k not in ["id", "name"]:
                            vendor_info[k] = v

            outsourced_items.append({
                "item_name": dish,
                "quantity": qty,
                "unit": unit,
                "vendor": vendor_info
            })
        else:
            in_house_dish_names.append(dish)

    recipe_qs = RecipeIngredient.objects.select_related("item", "ingredient__category").filter(
        item__branch_profile=session_obj.booking.branch_profile,
        item__name__in=in_house_dish_names,
    )

    for ri in recipe_qs:
        ingredient_name = ri.ingredient.name.strip()
        qty = float(ri.quantity or 0)
        unit = ri.unit or ""
        base_quantity, base_unit = normalize_quantity_unit(qty, unit)
        person_count = ri.person_count if ri.person_count and ri.person_count > 0 else DEFAULT_ESTIMATED_PERSONS
        scale_factor = Decimal(persons) / Decimal(person_count)

        total_ingredients[ingredient_name]["value"] += Decimal(str(base_quantity)) * scale_factor
        if base_unit:
            total_ingredients[ingredient_name]["unit"] = base_unit
        total_ingredients[ingredient_name]["used_in"].add(ri.item.name.strip())

    from ListOfIngridients.models import IngridientsItem
    # To support spelling variations like Tomato/Tomata, load all items and fallback via fuzzy matching
    items_with_categories = IngridientsItem.objects.select_related("category").filter(
        branch_profile=session_obj.booking.branch_profile
    )
    category_map = {item.name.strip().lower(): item.category.name for item in items_with_categories}

    from stockmanagement.models import StokeItem
    # To support spelling variations, load all stock items and then fuzzy-search names
    stock_items = StokeItem.objects.filter(branch_profile=session_obj.booking.branch_profile)
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
        assign.ingredient.name.strip().lower(): assign.vendor
        for assign in IngredientVendorAssignment.objects.filter(session=session_obj).select_related("vendor", "ingredient")
    }

    final_ingredients = {}
    for ingredient, data in total_ingredients.items():
        converted_value, converted_unit = to_readable_quantity_unit(
            float(data["value"]), data["unit"]
        )
        cat = category_map.get(ingredient.strip().lower(), "")
        if not cat:
            cat = fuzzy_lookup(ingredient, category_map, cutoff=0.6) or ""

        stock_info = stock_map.get(ingredient.strip().lower())
        if stock_info is None:
            stock_info = fuzzy_lookup(ingredient, stock_map, cutoff=0.6) or {}

        vendor_obj = ingredient_vendor_assignments.get(ingredient.strip().lower())
        if not vendor_obj:
            # Fuzzy match keys just in case
            keys = list(ingredient_vendor_assignments.keys())
            close = difflib.get_close_matches(ingredient.strip().lower(), [k.strip().lower() for k in keys], n=1, cutoff=0.6)
            if close:
                matched_key = keys[[k.strip().lower() for k in keys].index(close[0])]
                vendor_obj = ingredient_vendor_assignments.get(matched_key)
        
        vendor_info = None
        if vendor_obj:
            vendor_info = {
                "id": vendor_obj.id,
                "name": vendor_obj.name,
                "mobile_no": vendor_obj.mobile_no,
                "source_type": IngredientVendorAssignment.objects.filter(session=session_obj, ingredient__name__iexact=ingredient).first().source_type if IngredientVendorAssignment.objects.filter(session=session_obj, ingredient__name__iexact=ingredient).exists() else "manual"
            }

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
        branch_profile=session_obj.booking.branch_profile,
        category__is_common=True,
    ).select_related("category")
    common_names = [item.name for item in common_items]
    common_stock_items = StokeItem.objects.filter(
        branch_profile=session_obj.booking.branch_profile,
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

            vendor_obj = ingredient_vendor_assignments.get(key)
            vendor_info = {
                "id": vendor_obj.id,
                "name": vendor_obj.name,
                "mobile_no": vendor_obj.mobile_no,
            } if vendor_obj else None

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

    return final_ingredients, outsourced_items


class EventBookingViewSet(generics.GenericAPIView):
    serializer_class = EventBookingSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "event_bookings"

    def get_queryset(self):
        return filter_branch_queryset(EventBooking.objects.all(), self.request)

    def post(self, request):
        sessions = request.data.get("sessions", [])

        # Process each session's selected_items and extra_service
        for session in sessions:
            # Convert the selected_items payload for the session
            selected_items = session.get("selected_items", {})
            converted_payload = {
                key: [{"name": item} for item in value]
                for key, value in selected_items.items()
            }
            session["selected_items"] = converted_payload

            # Calculate extra_service_amount for the session
            extra_services = session.get("extra_service", [])
            amount = sum(_safe_amount(s.get("amount")) for s in extra_services)
            session["extra_service_amount"] = str(amount)

            # Calculate waiter_service_amount for the session.
            # waiter_service can arrive as a single dict {} or a list [{}] — normalise to list.
            raw_waiter = session.get("waiter_service", [])
            waiter_services = [raw_waiter] if isinstance(raw_waiter, dict) and raw_waiter else (raw_waiter if isinstance(raw_waiter, list) else [])
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
            self.get_queryset().prefetch_related(
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
                        sum(_safe_amount(s.get("amount")) for s in session.extra_service)
                    )
                    changed = True

                # Backfill waiter_service_amount if it was stored as "0" but has entries
                if (
                    session.waiter_service_amount in (None, "0")
                    and session.waiter_service
                ):
                    raw_ws = session.waiter_service
                    ws_list = [raw_ws] if isinstance(raw_ws, dict) and raw_ws else (raw_ws if isinstance(raw_ws, list) else [])
                    session.waiter_service_amount = str(
                        sum(_safe_amount(s.get("amount")) for s in ws_list)
                    )
                    changed = True

                if changed:
                    session.save()

        serializer = EventBookingSerializer(queryset, many=True)

        for event_data, event_obj in zip(serializer.data, queryset):
            if requested_session_id:
                event_data["sessions"] = [
                    session_data
                    for session_data in event_data.get("sessions", [])
                    if str(session_data.get("id")) == str(requested_session_id)
                ]

            sessions_by_id = {session.id: session for session in event_obj.sessions.all()}
            for session_data in event_data.get("sessions", []):
                session_obj = sessions_by_id.get(session_data.get("id"))
                if not session_obj:
                    continue
                final_ingredients, outsourced_items = calculate_ingredients_required(session_obj)
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
        return filter_branch_queryset(EventBooking.objects.all(), self.request)

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
                    ws_list = [raw_ws] if isinstance(raw_ws, dict) and raw_ws else (raw_ws if isinstance(raw_ws, list) else [])
                    if ws_list:
                        session["waiter_service_amount"] = str(
                            sum(_safe_amount(s.get("amount")) for s in ws_list)
                        )

                    if selected_items and isinstance(selected_items, dict):
                        # Some logic might pass already converted items, check if it's list of strings
                        is_unconverted = any(
                            isinstance(v, list) and len(v) > 0 and isinstance(v[0], str)
                            for v in selected_items.values()
                        )

                        if is_unconverted:
                            converted_payload = {
                                key: [{"name": item} for item in value]
                                for key, value in selected_items.items()
                            }
                            session["selected_items"] = converted_payload

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
            eventbooking = self.get_queryset().prefetch_related(
                "sessions__staff_assignments__staff__role",
                "sessions__staff_assignments__role_at_event",
                "sessions__ground_requirements__ground_item__category",
            ).get(pk=pk)
            serializer = EventBookingSerializer(eventbooking)

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

            sessions_by_id = {session.id: session for session in eventbooking.sessions.all()}
            for session_dict in response_data.get("sessions", []):
                session_obj = sessions_by_id.get(session_dict.get("id"))
                if not session_obj:
                    continue
                final_ingredients, outsourced_items = calculate_ingredients_required(session_obj)
                session_dict["ingredients_required"] = final_ingredients
                session_dict["outsourced_items"] = outsourced_items

            return Response(                {
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
        return filter_branch_queryset(EventBooking.objects.all(), self.request)

    def get(self, request):
        EventBooking.cancel_expired_pending_bookings()
        queryset = (
            self.get_queryset().prefetch_related(
                "sessions__staff_assignments__staff__role",
                "sessions__staff_assignments__role_at_event",
                "sessions__ground_requirements__ground_item__category",
            )
            .filter(status="pending")
            .order_by("-date")
        )
        serializer = EventBookingSerializer(queryset, many=True)
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
                session_id=session_id,
                item_name__iexact=item_name
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
        ingredient_name = payload.get("ingredient_name")
        session_id = _session_id_from_payload(payload)
        session = None
        if session_id:
            payload["session"] = session_id
            from .models import EventSession

            session = EventSession.objects.select_related("booking").get(id=session_id)
            ensure_object_in_user_branch(session.booking, request)
        
        # Look up ingredient by name to get its ID
        if ingredient_name:
            from ListOfIngridients.models import IngridientsItem
            ingredient_qs = IngridientsItem.objects.filter(name__iexact=ingredient_name)
            if session is not None:
                ingredient_qs = ingredient_qs.filter(
                    branch_profile=session.booking.branch_profile
                )
            ingredient_obj = ingredient_qs.first()
            if not ingredient_obj:
                return Response({"error": f"Ingredient '{ingredient_name}' not found"}, status=400)
            payload["ingredient"] = ingredient_obj.id

        ingredient_id = payload.get("ingredient")
        if ingredient_id and session_id:
            existing = IngredientVendorAssignment.objects.filter(
                ingredient_id=ingredient_id,
                session_id=session_id
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
