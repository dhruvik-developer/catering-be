import ast
from collections import defaultdict
from functools import lru_cache
import inspect
from importlib import import_module
import re

from django.apps import apps

HTTP_METHOD_PERMISSION_MAP = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

VIEWSET_METHOD_ACTION_PAIRS = (
    ("GET", "list"),
    ("GET", "retrieve"),
    ("POST", "create"),
    ("PUT", "update"),
    ("PATCH", "partial_update"),
    ("DELETE", "destroy"),
)

STANDARD_ACTION_ORDER = ("view", "create", "update", "delete")

TYPO_ALIASES = {
    "ingridients": "ingredients",
    "ingridient": "ingredient",
    "stoke": "stock",
}

# Maps "{app_label}.{ModelClassName}" to the view permission_resource a model is
# managed by, for cases where identity matching can't bridge the naming gap
# (e.g. RecipeIngredient ↔ recipes, Expense ↔ expense_entries).
EXPLICIT_MODEL_RESOURCE_OVERRIDES = {
    "item.RecipeIngredient": "recipes",
    "payments.TransactionHistory": "transactions",
    "eventstaff.FixedStaffSalaryPayment": "fixed_staff_payments",
    "Expense.Expense": "expense_entries",
    "Expense.Category": "expense_categories",
    "user.BranchProfile": "branch_profiles",
    "user.UserModel": "users",
}


def _humanize(value):
    return str(value).replace("_", " ").strip()


def _module_name(resource_code):
    return _humanize(resource_code).title()


def _module_description(resource_code):
    return f"Manage {_humanize(resource_code).lower()}."


def _permission_name(resource_code, action):
    return f"{_humanize(action).capitalize()} {_humanize(resource_code).lower()}"


def _singularize_word(value):
    if value.endswith("ies"):
        return f"{value[:-3]}y"
    if value.endswith("s") and not value.endswith("ss") and len(value) > 1:
        return value[:-1]
    return value


def _camel_to_snake(name):
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _apply_typo_aliases_per_token(snake_code):
    return "_".join(TYPO_ALIASES.get(token, token) for token in snake_code.split("_"))


def _model_base_resource(model):
    override_key = f"{model._meta.app_label}.{model.__name__}"
    explicit = EXPLICIT_MODEL_RESOURCE_OVERRIDES.get(override_key)
    if explicit:
        return explicit
    return _apply_typo_aliases_per_token(_camel_to_snake(model.__name__))


def _resource_identity(resource_code):
    normalized_text = str(resource_code).lower()
    for source, target in TYPO_ALIASES.items():
        normalized_text = normalized_text.replace(source, target)

    raw_tokens = [token for token in re.split(r"[_\W]+", normalized_text) if token]
    if not raw_tokens:
        raw_tokens = [normalized_text]

    normalized_tokens = [_singularize_word(token) for token in raw_tokens]
    normalized = "".join(normalized_tokens)
    return _singularize_word(normalized)


def _find_alias_model_resource(resource, catalog_dict, model_seeded_resources, resource_actions):
    target_identity = _resource_identity(resource)

    for candidate in model_seeded_resources:
        if candidate in resource_actions:
            continue
        if _resource_identity(candidate) == target_identity:
            return candidate

    return None


def _normalize_permission_codes(value, resource=None):
    if not value:
        return []

    raw_values = [value] if isinstance(value, str) else list(value)
    normalized = []

    for raw_code in raw_values:
        if not raw_code:
            continue

        code = str(raw_code).strip()
        if not code:
            continue

        if "." in code:
            normalized.append(code)
        elif resource:
            normalized.append(f"{resource}.{code}")

    return normalized


def _iter_all_view_classes():
    for app_config in apps.get_app_configs():
        module_name = f"{app_config.name}.views"

        try:
            module = import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue
            yield cls


def _iter_view_classes():
    for cls in _iter_all_view_classes():
        if getattr(cls, "permission_resource", None):
            yield cls


def _iter_direct_permission_codes_in_source():
    for view_cls in _iter_all_view_classes():
        try:
            source = inspect.getsource(view_cls)
        except OSError:
            continue

        try:
            module_ast = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(module_ast):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "user_has_permission":
                continue
            if len(node.args) < 2:
                continue

            permission_node = node.args[1]
            if isinstance(permission_node, ast.Constant) and isinstance(permission_node.value, str):
                permission_code = permission_node.value.strip()
                if "." in permission_code:
                    yield permission_code


def _get_method_permission_codes(view_cls, method, view_action=None):
    permission_action_map = getattr(view_cls, "permission_action_map", {}) or {}
    resource = getattr(view_cls, "permission_resource", None)

    if view_action and view_action in permission_action_map:
        return _normalize_permission_codes(permission_action_map[view_action], resource)

    if method in permission_action_map:
        return _normalize_permission_codes(permission_action_map[method], resource)

    if not resource:
        return []

    permission_action = getattr(view_cls, "permission_action", None)
    action = permission_action or HTTP_METHOD_PERMISSION_MAP.get(method)
    if not action:
        return []

    return [f"{resource}.{action}"]


def _iter_permission_codes_for_view(view_cls):
    permission_action_map = getattr(view_cls, "permission_action_map", {}) or {}
    resource = getattr(view_cls, "permission_resource", None)

    for mapped_value in permission_action_map.values():
        for code in _normalize_permission_codes(mapped_value, resource):
            yield code

    if getattr(view_cls, "permission_action", None) and resource:
        yield f"{resource}.{view_cls.permission_action}"

    try:
        from rest_framework.viewsets import ViewSetMixin

        is_view_set = issubclass(view_cls, ViewSetMixin)
    except Exception:
        is_view_set = False

    if is_view_set:
        for method, view_action in VIEWSET_METHOD_ACTION_PAIRS:
            if hasattr(view_cls, view_action):
                for code in _get_method_permission_codes(view_cls, method, view_action):
                    yield code
        return

    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        if hasattr(view_cls, method.lower()):
            for code in _get_method_permission_codes(view_cls, method):
                yield code


def _action_sort_key(action):
    if action in STANDARD_ACTION_ORDER:
        return (STANDARD_ACTION_ORDER.index(action), action)
    return (len(STANDARD_ACTION_ORDER), action)


@lru_cache(maxsize=1)
def build_permission_catalog():
    catalog_dict = {}
    model_seeded_resources = set()
    excluded_apps = {"admin", "auth", "contenttypes", "sessions", "authtoken", "accesscontrol"}

    # 1. Seed CRUD permissions from registered models using a normalized
    #    snake_case resource code derived from the CamelCase class name with
    #    typo aliases applied per token. Explicit overrides in
    #    EXPLICIT_MODEL_RESOURCE_OVERRIDES take precedence so models whose
    #    naming doesn't align with their view resource code (e.g. UserModel
    #    vs. users) get merged cleanly instead of duplicated.
    models = sorted(apps.get_models(), key=lambda m: (m._meta.app_label, m._meta.model_name))
    for model in models:
        if model._meta.app_label in excluded_apps:
            continue

        resource = _model_base_resource(model)
        if resource in catalog_dict:
            continue

        catalog_dict[resource] = {
            "code": resource,
            "name": _module_name(resource),
            "description": _module_description(resource),
            "permissions": {
                action: _permission_name(resource, action)
                for action in STANDARD_ACTION_ORDER
            },
        }
        model_seeded_resources.add(resource)

    # 2. Extract custom permissions and module actions from views/source
    resource_actions = defaultdict(set)
    for view_cls in _iter_view_classes():
        for permission_code in _iter_permission_codes_for_view(view_cls):
            if "." not in permission_code:
                continue

            resource, action = permission_code.split(".", 1)
            if resource and action:
                resource_actions[resource].add(action)

    for permission_code in _iter_direct_permission_codes_in_source():
        resource, action = permission_code.split(".", 1)
        if resource and action:
            resource_actions[resource].add(action)

    # 3. Merge parsed view permissions into the catalog
    for resource, actions in resource_actions.items():
        if resource not in catalog_dict:
            alias_model_resource = _find_alias_model_resource(
                resource=resource,
                catalog_dict=catalog_dict,
                model_seeded_resources=model_seeded_resources,
                resource_actions=resource_actions,
            )
            should_promote_model_resource = bool(alias_model_resource)

            if should_promote_model_resource:
                promoted_entry = catalog_dict.pop(alias_model_resource)
                promoted_entry["code"] = resource
                promoted_entry["name"] = _module_name(resource)
                promoted_entry["description"] = _module_description(resource)
                promoted_entry["permissions"] = {
                    action: _permission_name(resource, action)
                    for action in promoted_entry.get("permissions", {}).keys()
                }
                catalog_dict[resource] = promoted_entry
                model_seeded_resources.remove(alias_model_resource)
                model_seeded_resources.add(resource)
            else:
                catalog_dict[resource] = {
                    "code": resource,
                    "name": _module_name(resource),
                    "description": _module_description(resource),
                    "permissions": {}
                }
            
        for action in actions:
            if action not in catalog_dict[resource]["permissions"]:
                catalog_dict[resource]["permissions"][action] = _permission_name(resource, action)

    # 4. Finalize the list structure, sorting actions logically
    catalog = []
    for resource in sorted(catalog_dict.keys()):
        entry = catalog_dict[resource]
        sorted_actions = sorted(entry["permissions"].keys(), key=_action_sort_key)
        
        catalog.append({
            "code": entry["code"],
            "name": entry["name"],
            "description": entry["description"],
            "permissions": [
                (action, entry["permissions"][action])
                for action in sorted_actions
            ]
        })

    return catalog


def iter_catalog_permissions(catalog=None):
    catalog_rows = catalog if catalog is not None else build_permission_catalog()

    for module_index, module in enumerate(catalog_rows, start=1):
        for permission_index, permission in enumerate(module.get("permissions", []), start=1):
            action, name = permission
            yield {
                "module_code": module["code"],
                "module_name": module["name"],
                "module_description": module.get("description", ""),
                "module_sort_order": module_index,
                "permission_code": f"{module['code']}.{action}",
                "permission_action": action,
                "permission_name": name,
                "permission_description": f"{name} permission for {module['name'].lower()}.",
                "permission_sort_order": permission_index,
            }
