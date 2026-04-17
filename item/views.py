from rest_framework.response import Response
from rest_framework import status, generics
from radha.Utils.permissions import *
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

    def post(self, request):
        if Item.objects.filter(name=request.data.get("name")).exists():
            return Response(
                {"status": False, "message": "Item already exists", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ItemSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
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
            Item.objects.select_related("category")
            .prefetch_related("recipe_ingredients__ingredient__category")
            .all()
        )
        serializer = ItemSerializer(items, many=True)
        return Response(
            {"status": True, "message": "Item list", "data": serializer.data},
            status=status.HTTP_200_OK,
        )


class ItemGetViewSet(generics.GenericAPIView):
    serializer_class = ItemDetailSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get(self, request, pk=None):
        try:
            item = (
                Item.objects.select_related("category")
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
            item = Item.objects.get(pk=pk)
            serializer = ItemSerializer(item, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
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
            item = Item.objects.get(pk=pk)
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

    def get(self, request, item_id=None):
        item_id = item_id or request.query_params.get("item_id")
        queryset = RecipeIngredient.objects.select_related("item", "ingredient__category").all()

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

    def get_object(self, pk):
        return RecipeIngredient.objects.select_related("item", "ingredient__category").get(pk=pk)

    def get(self, request, pk=None):
        try:
            recipe = self.get_object(pk)
            serializer = RecipeIngredientSerializer(recipe)
            return Response({"status": True, "message": "Recipe retrieved", "data": serializer.data})
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found", "data": {}}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk=None):
        try:
            recipe = RecipeIngredient.objects.get(pk=pk)
            serializer = RecipeIngredientCreateSerializer(recipe, data=request.data, partial=True)
            if serializer.is_valid(raise_exception=True):
                serializer.save()
                return Response({"status": True, "message": "Recipe updated", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"status": False, "message": "Validation error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found", "data": {}}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk=None):
        try:
            recipe = RecipeIngredient.objects.get(pk=pk)
            recipe.delete()
            return Response({"status": True, "message": "Recipe deleted"}, status=status.HTTP_204_NO_CONTENT)
        except RecipeIngredient.DoesNotExist:
            return Response({"status": False, "message": "Recipe not found"}, status=status.HTTP_404_NOT_FOUND)



