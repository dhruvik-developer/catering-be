from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from datetime import datetime, timedelta
from .models import Expense, Category, ExpenseEntity
from .serializers import ExpenseSerializer, CategorySerializer, ExpenseEntitySerializer
from radha.Utils.permissions import IsAdminUserOrReadOnly


class ExpenseView(generics.GenericAPIView):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_entries"

    def get_queryset(self):
        # Prefetch category and entity for performance improvement
        return Expense.objects.select_related("category", "entity").order_by("-date")

    def get(self, request):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "status": True,
                "message": "Expense list retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Expense created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "status": False,
                "message": "Validation error",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ExpenseDetailView(generics.GenericAPIView):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_entries"

    def get_object(self, pk):
        return get_object_or_404(Expense, pk=pk)

    def get(self, request, pk=None):
        expense = self.get_object(pk)
        serializer = self.get_serializer(expense)

        return Response(
            {
                "status": True,
                "message": "Expense retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None):
        expense = self.get_object(pk)
        serializer = self.get_serializer(expense, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Expense updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": False,
                "message": "Validation error",
                "data": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, pk=None):
        expense = self.get_object(pk)
        expense.delete()

        return Response(
            {
                "status": True,
                "message": "Expense deleted successfully",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )


class CategoryView(generics.GenericAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_categories"

    def get(self, request):
        queryset = Category.objects.all().order_by("name")
        serializer = self.serializer_class(queryset, many=True)

        return Response(
            {
                "status": True,
                "message": "Category list retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Category created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )


class CategoryDetailView(generics.GenericAPIView):
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_categories"

    def get_object(self, pk):
        try:
            return Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            return None

    def get(self, request, pk=None):
        category = self.get_object(pk)
        if not category:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(category)
        return Response(
            {
                "status": True,
                "message": "Category retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None):
        category = self.get_object(pk)
        if not category:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(category, data=request.data, partial=True)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Category updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

    def delete(self, request, pk=None):
        category = self.get_object(pk)
        if not category:
            return Response(
                {
                    "status": False,
                    "message": "Category not found",
                    "data": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Optional safety: prevent delete if expenses exist
        if category.expenses.exists():
            return Response(
                {
                    "status": False,
                    "message": "Cannot delete category with linked expenses",
                    "data": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        category.delete()

        return Response(
            {
                "status": True,
                "message": "Category deleted successfully",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )


class ExpenseEntityView(generics.GenericAPIView):
    serializer_class = ExpenseEntitySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_entities"

    def get(self, request):
        queryset = ExpenseEntity.objects.all().order_by("name")
        entity_type = request.query_params.get("entity_type")
        if entity_type:
             queryset = queryset.filter(entity_type=entity_type)
             
        serializer = self.serializer_class(queryset, many=True)

        return Response(
            {
                "status": True,
                "message": "Expense Entity list retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Expense Entity created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

class ExpenseEntityDetailView(generics.GenericAPIView):
    serializer_class = ExpenseEntitySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_entities"

    def get_object(self, pk):
        try:
            return ExpenseEntity.objects.get(pk=pk)
        except ExpenseEntity.DoesNotExist:
            return None

    def get(self, request, pk=None):
        entity = self.get_object(pk)
        if not entity:
            return Response(
                {"status": False, "message": "Expense Entity not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(entity)
        return Response(
            {
                "status": True,
                "message": "Expense Entity retrieved successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk=None):
        entity = self.get_object(pk)
        if not entity:
            return Response(
                {"status": False, "message": "Expense Entity not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(entity, data=request.data, partial=True)

        if serializer.is_valid(raise_exception=True):
            serializer.save()
            return Response(
                {
                    "status": True,
                    "message": "Expense Entity updated successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

    def delete(self, request, pk=None):
        entity = self.get_object(pk)
        if not entity:
            return Response(
                {"status": False, "message": "Expense Entity not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        entity.delete()

        return Response(
            {"status": True, "message": "Expense Entity deleted successfully", "data": {}},
            status=status.HTTP_200_OK,
        )


class ExpenseEntitySummaryView(APIView):
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "expense_summaries"

    def get(self, request, pk):
        try:
            entity = ExpenseEntity.objects.get(pk=pk)
        except ExpenseEntity.DoesNotExist:
            return Response(
                {"status": False, "message": "Expense Entity not found", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
            
        period = request.query_params.get("period", "all") # all, month, year
        
        expenses = Expense.objects.filter(entity=entity)
        
        today = datetime.now().date()
        if period == "month":
            start_date = today.replace(day=1)
            expenses = expenses.filter(date__gte=start_date)
        elif period == "year":
            start_date = today.replace(month=1, day=1)
            expenses = expenses.filter(date__gte=start_date)
            
        total_amount = expenses.aggregate(total=Sum('amount'))['total'] or 0
        
        # Serialize the associated expenses
        serializer = ExpenseSerializer(expenses.order_by("-date"), many=True)
        
        return Response(
            {
                "status": True,
                "message": "Entity expense summary retrieved",
                "data": {
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "entity_type": entity.entity_type,
                    "period": period,
                    "total_amount": total_amount,
                    "expenses": serializer.data
                },
            },
            status=status.HTTP_200_OK,
        )
