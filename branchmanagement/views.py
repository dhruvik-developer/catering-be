from rest_framework import generics, status
from django.db.models import Q
from django.db import transaction
from rest_framework.response import Response

from radha.Utils.permissions import IsAdminUserOrReadOnly

from .models import (
    BranchFormat,
    PartyInformation,
    GlobalConfiguration,
    BranchItem,
    BranchBill,
)
from .serializers import (
    BranchFormatSerializer,
    PartyInformationSerializer,
    GlobalConfigurationSerializer,
    BranchItemSerializer,
    BranchBillSerializer,
)


class InvoiceSetupListCreateAPIView(generics.GenericAPIView):
    serializer_class = BranchFormatSerializer
    queryset = BranchFormat.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "invoice_setup"

    def get_queryset(self):
        queryset = super().get_queryset()
        is_active = self.request.query_params.get("is_active")

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Branch formats fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _normalize_signature_value(value):
        if value is None:
            return ""
        if not isinstance(value, str):
            value = str(value)
        return value.strip()

    def _build_branch_signature(self, branch_data):
        branch_name = self._normalize_signature_value(branch_data.get("branch_name")).lower()
        address = self._normalize_signature_value(branch_data.get("address")).lower()
        gst_number = self._normalize_signature_value(branch_data.get("gst_number")).upper()
        return branch_name, address, gst_number

    def _build_branch_identity(self, branch_data):
        branch_name = self._normalize_signature_value(branch_data.get("branch_name")).lower()
        address = self._normalize_signature_value(branch_data.get("address")).lower()
        return branch_name, address

    def post(self, request):
        branches_payload = request.data.get("branches")

        if isinstance(branches_payload, list):
            created_branches = []
            skipped_branches = []

            existing_signatures = set()
            existing_identities = set()
            for branch in BranchFormat.objects.all().only("branch_name", "address", "gst_number"):
                identity = (
                    (branch.branch_name or "").strip().lower(),
                    (branch.address or "").strip().lower(),
                )
                existing_identities.add(identity)
                existing_signatures.add(
                    (
                        identity[0],
                        identity[1],
                        (branch.gst_number or "").strip().upper(),
                    )
                )

            with transaction.atomic():
                for branch_data in branches_payload:
                    if not isinstance(branch_data, dict):
                        return Response(
                            {
                                "status": False,
                                "message": "Each branch entry must be an object.",
                                "data": {},
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    signature = self._build_branch_signature(branch_data)
                    identity = self._build_branch_identity(branch_data)

                    if signature in existing_signatures or identity in existing_identities:
                        skipped_branches.append(branch_data)
                        continue

                    serializer = self.get_serializer(data=branch_data)
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    created_branches.append(serializer.data)
                    existing_signatures.add(signature)
                    existing_identities.add(identity)

            return Response(
                {
                    "status": True,
                    "message": "Branch formats processed successfully.",
                    "data": {
                        "created_branches": created_branches,
                        "created_count": len(created_branches),
                        "skipped_count": len(skipped_branches),
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch format created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class InvoiceSetupDetailAPIView(generics.GenericAPIView):
    serializer_class = BranchFormatSerializer
    queryset = BranchFormat.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "invoice_setup"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        branch_format = self.get_object(pk)
        if not branch_format:
            return Response(
                {"status": False, "message": "Branch format not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(branch_format)
        return Response(
            {
                "status": True,
                "message": "Branch format fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        branch_format = self.get_object(pk)
        if not branch_format:
            return Response(
                {"status": False, "message": "Branch format not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(branch_format, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch format updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        branch_format = self.get_object(pk)
        if not branch_format:
            return Response(
                {"status": False, "message": "Branch format not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(branch_format, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch format updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        branch_format = self.get_object(pk)
        if not branch_format:
            return Response(
                {"status": False, "message": "Branch format not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        branch_format.delete()
        return Response(
            {"status": True, "message": "Branch format deleted successfully.", "data": {}},
            status=status.HTTP_200_OK,
        )


class PartyInformationListCreateAPIView(generics.GenericAPIView):
    serializer_class = PartyInformationSerializer
    queryset = PartyInformation.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "party_information"

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        is_active = self.request.query_params.get("is_active")

        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(party_name__icontains=search)
                | Q(party_code__icontains=search)
                | Q(party_gst_no__icontains=search)
                | Q(invoice_prefix__icontains=search)
            )

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Party information fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Party information created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class PartyInformationDetailAPIView(generics.GenericAPIView):
    serializer_class = PartyInformationSerializer
    queryset = PartyInformation.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "party_information"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        party = self.get_object(pk)
        if not party:
            return Response(
                {"status": False, "message": "Party information not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(party)
        return Response(
            {
                "status": True,
                "message": "Party information fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        party = self.get_object(pk)
        if not party:
            return Response(
                {"status": False, "message": "Party information not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(party, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Party information updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        party = self.get_object(pk)
        if not party:
            return Response(
                {"status": False, "message": "Party information not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(party, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Party information updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        party = self.get_object(pk)
        if not party:
            return Response(
                {"status": False, "message": "Party information not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        party.delete()
        return Response(
            {"status": True, "message": "Party information deleted successfully.", "data": {}},
            status=status.HTTP_200_OK,
        )


class GlobalConfigurationListCreateAPIView(generics.GenericAPIView):
    serializer_class = GlobalConfigurationSerializer
    queryset = GlobalConfiguration.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "global_configuration"

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")

        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(default_hsn_code__icontains=search) |
                Q(available_gst_percentages__icontains=search)
            )

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)

        return Response(
            {
                "status": True,
                "message": "Global configurations fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Global configuration created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
    serializer_class = GlobalConfigurationSerializer
    queryset = GlobalConfiguration.objects.all()

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)

        return Response(
            {
                "status": True,
                "message": "Global configurations fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Global configuration created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )
    serializer_class = GlobalConfigurationSerializer

    def get_object(self):
        obj, created = GlobalConfiguration.objects.get_or_create(id=1)
        return obj

    def get(self, request):
        obj = self.get_object()
        serializer = self.get_serializer(obj)
        return Response(serializer.data)

    def post(self, request):
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request):
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class GlobalConfigurationDetailAPIView(generics.GenericAPIView):
    serializer_class = GlobalConfigurationSerializer
    queryset = GlobalConfiguration.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "global_configuration"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"status": False, "message": "Global configuration not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(obj)
        return Response(
            {
                "status": True,
                "message": "Global configuration fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"status": False, "message": "Global configuration not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Global configuration updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"status": False, "message": "Global configuration not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Global configuration updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response(
                {"status": False, "message": "Global configuration not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        obj.delete()

        return Response(
            {
                "status": True,
                "message": "Global configuration deleted successfully.",
                "data": {},
            },
            status=status.HTTP_200_OK,
        )

class BranchItemListCreateAPIView(generics.GenericAPIView):
    serializer_class = BranchItemSerializer
    queryset = BranchItem.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "branch_items"

    def get_queryset(self):
        queryset = super().get_queryset()
        branch_id = self.request.query_params.get("branch")
        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Branch items fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Branch item created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class BranchItemDetailAPIView(generics.GenericAPIView):
    serializer_class = BranchItemSerializer
    queryset = BranchItem.objects.all()
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "branch_items"

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Branch item not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(item)
        return Response(
            {
                "status": True,
                "message": "Branch item fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Branch item not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch item updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Branch item not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch item updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk):
        item = self.get_object(pk)
        if not item:
            return Response(
                {"status": False, "message": "Branch item not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        item.delete()
        return Response(
            {"status": True, "message": "Branch item deleted successfully.", "data": {}},
            status=status.HTTP_200_OK,
        )


class BranchBillListCreateAPIView(generics.GenericAPIView):
    serializer_class = BranchBillSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "branch_bills"

    def get_queryset(self):
        queryset = BranchBill.objects.select_related(
            "branch",
            "branch__bank_details",
            "party",
        ).prefetch_related("items__branch_item")
        branch_id = self.request.query_params.get("branch")
        party_id = self.request.query_params.get("party")
        invoice_number = self.request.query_params.get("invoice_number")

        if branch_id:
            queryset = queryset.filter(branch_id=branch_id)
        if party_id:
            queryset = queryset.filter(party_id=party_id)
        if invoice_number:
            queryset = queryset.filter(invoice_number__icontains=invoice_number.strip())

        return queryset

    def get(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(
            {
                "status": True,
                "message": "Branch bills fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "status": True,
                "message": "Branch bill created successfully.",
                "data": self.get_serializer(serializer.instance).data,
            },
            status=status.HTTP_201_CREATED,
        )


class BranchBillDetailAPIView(generics.GenericAPIView):
    serializer_class = BranchBillSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    permission_resource = "branch_bills"

    def get_queryset(self):
        return BranchBill.objects.select_related(
            "branch",
            "branch__bank_details",
            "party",
        ).prefetch_related("items__branch_item")

    def get_object(self, pk):
        return self.get_queryset().filter(pk=pk).first()

    def get(self, request, pk):
        bill = self.get_object(pk)
        if not bill:
            return Response(
                {"status": False, "message": "Branch bill not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(bill)
        return Response(
            {
                "status": True,
                "message": "Branch bill fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, pk):
        bill = self.get_object(pk)
        if not bill:
            return Response(
                {"status": False, "message": "Branch bill not found.", "data": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(bill, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "status": True,
                "message": "Branch bill updated successfully.",
                "data": self.get_serializer(serializer.instance).data,
            },
            status=status.HTTP_200_OK,
        )
