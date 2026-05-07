from rest_framework.response import Response
from rest_framework import status, generics
from radha.Utils.permissions import *
from user.branching import (
    ensure_object_in_user_branch,
    filter_branch_queryset,
    get_branch_save_kwargs,
)
from category.models import Category
from .models import Item, RecipeIngredient
from .serializers import (
    ItemSerializer,
    ItemDetailSerializer,
    RecipeIngredientSerializer,
    RecipeIngredientCreateSerializer,
)


class ItemViewSet(generics.GenericAPIView):
    serializer_class = ItemSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "items"

    def get_queryset(self):
        return filter_branch_queryset(Item.objects.all(), self.request)

    def post(self, request):
        category = None
        if request.data.get("category"):
            category = filter_branch_queryset(
                Category.objects.all(),
                request,
            ).get(id=request.data.get("category"))
            ensure_object_in_user_branch(category, request)

        if self.get_queryset().filter(name=request.data.get("name")).exists():
            return Response(
                {"status": False, "message": "Item already exists", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ItemSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            branch_kwargs = (
                {"branch_profile": category.branch_profile}
                if category is not None
                else get_branch_save_kwargs(request)
            )
            serializer.save(**branch_kwargs)
            return Response(
                {"status": True, "message": "Item created successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"status": False, "message": "Something went wrong", "data": {}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        items = (
            self.get_queryset().select_related("category", "branch_profile")
            .prefetch_related("recipe_ingredients__ingredient__category")
        )
        serializer = ItemSerializer(items, many=True)
        return Response(
            {"status": True, "message": "Item list", "data": serializer.data},
            status=status.HTTP_200_OK,
        )


class ItemGetViewSet(generics.GenericAPIView):
    serializer_class = ItemDetailSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "items"

    def get_queryset(self):
        return filter_branch_queryset(Item.objects.all(), self.request)

    def get(self, request, pk=None):
        try:
            item = (
                self.get_queryset().select_related("category", "branch_profile")
                .prefetch_related("recipe_ingredients__ingredient__category")
                .get(pk=pk)
            )
            serializer = ItemDetailSerializer(item)
            return Response(
                {"status": True, "message": "Item retrieved successfully", "data": serializer.data},
                status=status.HTTP_200_OK,
            )
        except Item.DoesNotExist:
            return Response(
                {"status": False, "message": "Item not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

    def put(self, request, pk=None):
        try:
            item = self.get_queryset().get(pk=pk)
            serializer = ItemSerializer(item, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                category = serializer.validated_data.get("category")
                if category:
                    ensure_object_in_user_branch(category, request)
                serializer.save()
                return Response(
                    {"status": True, "message": "Item updated successfully", "data": serializer.data},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"status": False, "message": "Something went wrong", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Item.DoesNotExist:
            return Response(
                {"status": False, "message": "Item not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

    def delete(self, request, pk=None):
        try:
            item = self.get_queryset().get(pk=pk)
            item.delete()
            return Response(
                {"status": True, "message": "Item deleted successfully", "data": {}},
                status=status.HTTP_204_NO_CONTENT,
            )
        except Item.DoesNotExist:
            return Response(
                {"status": False, "message": "Item not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )


class RecipeIngredientViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "recipes"

    def get(self, request, item_id=None):
        item_id = item_id or request.query_params.get("item_id")
        queryset = RecipeIngredient.objects.select_related("item", "ingredient__category")
        queryset = filter_branch_queryset(queryset, request, field_name="item__branch_profile")

        if item_id:
            queryset = queryset.filter(item_id=item_id)

        serializer = RecipeIngredientSerializer(queryset, many=True)
        return Response(
            {"status": True, "message": "Recipe list", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = RecipeIngredientCreateSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            ensure_object_in_user_branch(serializer.validated_data["item"], request)
            ingredient = serializer.validated_data["ingredient"]
            if ingredient.branch_profile_id != serializer.validated_data["item"].branch_profile_id:
                return Response(
                    {
                        "status": False,
                        "message": "Ingredient and item must belong to the same branch.",
                        "data": {},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer.save()
            return Response(
                {"status": True, "message": "Recipe Ingredient created successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"status": False, "message": "Validation error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class RecipeIngredientDetailViewSet(generics.GenericAPIView):
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "recipes"

    def get_object(self, pk):
        queryset = RecipeIngredient.objects.select_related("item", "ingredient__category")
        queryset = filter_branch_queryset(
            queryset,
            self.request,
            field_name="item__branch_profile",
        )
        return queryset.get(pk=pk)

    def get(self, request, pk=None):
        try:
            recipe = self.get_object(pk)
            serializer = RecipeIngredientSerializer(recipe)
            return Response({"status": True, "message": "Recipe retrieved", "data": serializer.data})
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found", "data": {}}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk=None):
        try:
            recipe = self.get_object(pk)
            serializer = RecipeIngredientCreateSerializer(recipe, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                ensure_object_in_user_branch(serializer.validated_data.get("item", recipe.item), request)
                item = serializer.validated_data.get("item", recipe.item)
                ingredient = serializer.validated_data.get("ingredient", recipe.ingredient)
                if ingredient.branch_profile_id != item.branch_profile_id:
                    return Response(
                        {
                            "status": False,
                            "message": "Ingredient and item must belong to the same branch.",
                            "data": {},
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                serializer.save()
                return Response({"status": True, "message": "Recipe updated", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"status": False, "message": "Validation error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found", "data": {}}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk=None):
        try:
            recipe = self.get_object(pk)
            recipe.delete()
            return Response({"status": True, "message": "Recipe deleted"}, status=status.HTTP_204_NO_CONTENT)
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found"}, status=status.HTTP_404_NOT_FOUND)


