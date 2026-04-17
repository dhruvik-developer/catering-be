from rest_framework import serializers

from .models import (
    BranchBankDetails,
    BranchFormat,
    PartyInformation,
    GlobalConfiguration,
    BranchItem,
    BranchBill,
    BranchBillItem,
)
import re
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction


class BranchBankDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchBankDetails
        fields = [
            "bank_name",
            "account_number",
            "ifsc_code",
            "account_holder_name",
        ]
        extra_kwargs = {
            "bank_name": {"required": False, "allow_blank": True},
            "account_number": {"required": False, "allow_blank": True},
            "ifsc_code": {"required": False, "allow_blank": True},
            "account_holder_name": {"required": False, "allow_blank": True},
        }

    def to_internal_value(self, data):
        data = data.copy()

        if "bank_name" in data and isinstance(data.get("bank_name"), str):
            data["bank_name"] = data["bank_name"].strip()
        if "account_number" in data and isinstance(data.get("account_number"), str):
            data["account_number"] = data["account_number"].strip()
        if "ifsc_code" in data and isinstance(data.get("ifsc_code"), str):
            data["ifsc_code"] = data["ifsc_code"].strip().upper()
        if "account_holder_name" in data and isinstance(data.get("account_holder_name"), str):
            data["account_holder_name"] = data["account_holder_name"].strip()

        return super().to_internal_value(data)


class BranchFormatSerializer(serializers.ModelSerializer):
    bank_details = BranchBankDetailsSerializer(required=False, allow_null=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = BranchFormat
        fields = [
            "id",
            "branch_name",
            "branch_code",
            "display_name",
            "address",
            "gst_number",
            "bank_details",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "branch_code", "display_name", "created_at", "updated_at"]

    def to_internal_value(self, data):
        data = data.copy()

        if "branch_name" in data and isinstance(data.get("branch_name"), str):
            data["branch_name"] = data["branch_name"].strip()
        if "address" in data and isinstance(data.get("address"), str):
            data["address"] = data["address"].strip()
        if "gst_number" in data and isinstance(data.get("gst_number"), str):
            normalized_gst = data["gst_number"].strip().upper()
            data["gst_number"] = normalized_gst or None
        if "bank_details" in data and isinstance(data.get("bank_details"), dict):
            bank_details = data["bank_details"].copy()
            normalized_bank_details = {}
            for key in ["bank_name", "account_number", "ifsc_code", "account_holder_name"]:
                value = bank_details.get(key)
                if isinstance(value, str):
                    value = value.strip()
                normalized_bank_details[key] = value

            has_any_value = any(
                value not in (None, "")
                for value in normalized_bank_details.values()
            )
            data["bank_details"] = normalized_bank_details if has_any_value else None

        return super().to_internal_value(data)

    def create(self, validated_data):
        bank_details = validated_data.pop("bank_details", None)
        branch = BranchFormat.objects.create(**validated_data)

        if bank_details:
            BranchBankDetails.objects.create(branch=branch, **bank_details)

        return branch

    def update(self, instance, validated_data):
        bank_details = validated_data.pop("bank_details", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if bank_details is not None:
            BranchBankDetails.objects.update_or_create(
                branch=instance,
                defaults=bank_details,
            )

        return instance

    def validate_branch_name(self, value):
        if not value:
            raise serializers.ValidationError("Branch name is required.")
        return value

    # def validate_gst_number(self, value):
    #     if not value:
    #         return value

    #     gstin = value.upper()

    #     pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'
    #     if not re.match(pattern, gstin):
    #         raise serializers.ValidationError("Invalid GST format.")

    #     chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    #     factor = 2
    #     total = 0

    #     for char in reversed(gstin[:-1]):
    #         code_point = chars.index(char)
    #         digit = factor * code_point
    #         factor = 1 if factor == 2 else 2
    #         digit = (digit // 36) + (digit % 36)
    #         total += digit

    #     check_code_point = (36 - (total % 36)) % 36
    #     if gstin[-1] != chars[check_code_point]:
    #         raise serializers.ValidationError("Invalid GST checksum.")

    #     return gstin


class PartyInformationSerializer(serializers.ModelSerializer):
    next_invoice_preview = serializers.CharField(read_only=True)

    class Meta:
        model = PartyInformation
        fields = [
            "id",
            "party_name",
            "party_gst_no",
            "party_code",
            "invoice_prefix",
            "next_sequence_no",
            "next_invoice_preview",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "next_invoice_preview", "created_at", "updated_at"]

    def to_internal_value(self, data):
        data = data.copy()

        if "party_name" in data and isinstance(data.get("party_name"), str):
            data["party_name"] = data["party_name"].strip()
        if "party_gst_no" in data and isinstance(data.get("party_gst_no"), str):
            normalized_gst = data["party_gst_no"].strip().upper()
            data["party_gst_no"] = normalized_gst or None
        if "party_code" in data and isinstance(data.get("party_code"), str):
            data["party_code"] = data["party_code"].strip().upper()
        if "invoice_prefix" in data and isinstance(data.get("invoice_prefix"), str):
            normalized_prefix = data["invoice_prefix"].strip().upper()
            data["invoice_prefix"] = normalized_prefix or None

        return super().to_internal_value(data)

    def validate_party_name(self, value):
        if not value:
            raise serializers.ValidationError("Party name is required.")
        return value

    def validate(self, attrs):
        invoice_prefix = attrs.get(
            "invoice_prefix",
            self.instance.invoice_prefix if self.instance else None,
        )
        if not invoice_prefix:
            raise serializers.ValidationError(
                {"invoice_prefix": "Invoice prefix is required."}
            )
        return attrs

    def validate_invoice_prefix(self, value):
        if not value:
            raise serializers.ValidationError("Invoice prefix is required.")
        return value

class GlobalConfigurationSerializer(serializers.ModelSerializer):

    class Meta:
        model = GlobalConfiguration
        fields = "__all__"

    def validate_available_gst_percentages(self, value):
        try:
            gst_list = [int(x.strip()) for x in value.split(",")]

            for gst in gst_list:
                if gst < 0 or gst > 100:
                    raise serializers.ValidationError(
                        "GST must be between 0 and 100."
                    )

        except ValueError:
            raise serializers.ValidationError(
                "Invalid format. Use comma separated numbers (e.g. 0,5,12)"
            )

        return value

    def validate(self, data):
        instance = getattr(self, "instance", None)

        available = data.get(
            "available_gst_percentages",
            instance.available_gst_percentages if instance else None
        )

        default = data.get(
            "default_gst_percentage",
            instance.default_gst_percentage if instance else None
        )

        if available and default is not None:
            gst_list = [int(x.strip()) for x in available.split(",")]

            if default not in gst_list:
                raise serializers.ValidationError(
                    "Default GST must be in available GST list."
                )

        return data

        return data

class BranchItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchItem
        fields = ["id", "branch", "name", "rate", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        if not value:
            raise serializers.ValidationError("Item name is required.")
        return value.strip()


class BranchBillItemSerializer(serializers.ModelSerializer):
    branch_item_name = serializers.CharField(source="branch_item.name", read_only=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    class Meta:
        model = BranchBillItem
        fields = [
            "id",
            "branch_item",
            "branch_item_name",
            "item_name",
            "quantity",
            "rate",
            "is_rate_inclusive",
            "gst_percentage",
            "taxable_amount",
            "sgst_amount",
            "cgst_amount",
            "amount",
            "sort_order",
        ]
        read_only_fields = [
            "id",
            "item_name",
            "taxable_amount",
            "sgst_amount",
            "cgst_amount",
            "amount",
        ]
        extra_kwargs = {
            "rate": {"required": False},
            "is_rate_inclusive": {"required": False},
            "gst_percentage": {"required": False},
            "sort_order": {"required": False},
        }


class BranchBillBranchSerializer(serializers.ModelSerializer):
    bank_details = BranchBankDetailsSerializer(read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = BranchFormat
        fields = [
            "id",
            "branch_name",
            "branch_code",
            "display_name",
            "address",
            "gst_number",
            "bank_details",
            "is_active",
        ]


class BranchBillPartySerializer(serializers.ModelSerializer):
    next_invoice_preview = serializers.CharField(read_only=True)

    class Meta:
        model = PartyInformation
        fields = [
            "id",
            "party_name",
            "party_gst_no",
            "party_code",
            "invoice_prefix",
            "next_sequence_no",
            "next_invoice_preview",
            "is_active",
        ]


class BranchBillSerializer(serializers.ModelSerializer):
    items = BranchBillItemSerializer(many=True)

    class Meta:
        model = BranchBill
        fields = [
            "id",
            "branch",
            "party",
            "invoice_number",
            "invoice_date",
            "order_number",
            "order_date",
            "hsn_code",
            "refrance",
            "taxable_amount",
            "output_sgst_total",
            "output_cgst_total",
            "round_off",
            "final_payable_amount",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "taxable_amount",
            "output_sgst_total",
            "output_cgst_total",
            "final_payable_amount",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "invoice_number": {"required": False, "allow_blank": True},
            "order_number": {"required": False, "allow_blank": True, "allow_null": True},
            "order_date": {"required": False, "allow_null": True},
            "hsn_code": {"required": False, "allow_blank": True, "allow_null": True},
            "refrance": {"required": False, "allow_blank": True, "allow_null": True},
            "round_off": {"required": False},
            "notes": {"required": False, "allow_blank": True},
        }

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one bill item is required.")
        return value

    @staticmethod
    def _quantize(value):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _resolve_invoice_number(self, validated_data):
        invoice_number = validated_data.get("invoice_number")
        party = validated_data["party"]

        if invoice_number:
            return invoice_number.strip().upper()

        if not party.invoice_prefix:
            raise serializers.ValidationError(
                {"invoice_number": "Invoice number or party invoice prefix is required."}
            )

        return f"{party.invoice_prefix}{party.next_sequence_no}"

    def _calculate_item_amounts(self, quantity, rate, gst_percentage, is_rate_inclusive):
        line_base_amount = self._quantize(quantity * rate)

        if not gst_percentage:
            return (
                line_base_amount,
                Decimal("0.00"),
                Decimal("0.00"),
                line_base_amount,
            )

        if is_rate_inclusive:
            taxable_amount = self._quantize(
                line_base_amount * Decimal("100") / (Decimal("100") + gst_percentage)
            )
            total_gst_amount = self._quantize(line_base_amount - taxable_amount)
            amount = line_base_amount
        else:
            taxable_amount = line_base_amount
            total_gst_amount = self._quantize(
                taxable_amount * gst_percentage / Decimal("100")
            )
            amount = self._quantize(taxable_amount + total_gst_amount)

        sgst_amount = self._quantize(total_gst_amount / Decimal("2"))
        cgst_amount = self._quantize(total_gst_amount - sgst_amount)

        return taxable_amount, sgst_amount, cgst_amount, amount

    def _build_items(self, bill, branch, items_data):
        line_items = []
        taxable_total = Decimal("0.00")
        sgst_total = Decimal("0.00")
        cgst_total = Decimal("0.00")

        for index, item_data in enumerate(items_data, start=1):
            branch_item = item_data["branch_item"]
            if branch_item.branch_id != branch.id:
                raise serializers.ValidationError(
                    {
                        "items": [
                            f"Branch item {branch_item.id} does not belong to branch {branch.id}."
                        ]
                    }
                )

            quantity = self._quantize(item_data["quantity"])
            rate = self._quantize(item_data.get("rate") or branch_item.rate)
            gst_percentage = self._quantize(item_data.get("gst_percentage", Decimal("0.00")))
            is_rate_inclusive = item_data.get("is_rate_inclusive", False)
            taxable_amount, sgst_amount, cgst_amount, line_amount = self._calculate_item_amounts(
                quantity=quantity,
                rate=rate,
                gst_percentage=gst_percentage,
                is_rate_inclusive=is_rate_inclusive,
            )

            taxable_total += taxable_amount
            sgst_total += sgst_amount
            cgst_total += cgst_amount

            line_items.append(
                BranchBillItem(
                    bill=bill,
                    branch_item=branch_item,
                    item_name=branch_item.name,
                    quantity=quantity,
                    rate=rate,
                    is_rate_inclusive=is_rate_inclusive,
                    gst_percentage=gst_percentage,
                    taxable_amount=taxable_amount,
                    sgst_amount=sgst_amount,
                    cgst_amount=cgst_amount,
                    amount=line_amount,
                    sort_order=item_data.get("sort_order") or index,
                )
            )

        return (
            line_items,
            self._quantize(taxable_total),
            self._quantize(sgst_total),
            self._quantize(cgst_total),
        )

    def _recalculate_bill_totals(self, bill, taxable_total, sgst_total, cgst_total, round_off):
        bill.taxable_amount = taxable_total
        bill.output_sgst_total = sgst_total
        bill.output_cgst_total = cgst_total
        bill.final_payable_amount = self._quantize(
            taxable_total + sgst_total + cgst_total + round_off
        )
        bill.save(
            update_fields=[
                "taxable_amount",
                "output_sgst_total",
                "output_cgst_total",
                "final_payable_amount",
                "updated_at",
            ]
        )

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        party = validated_data["party"]
        validated_data["invoice_number"] = self._resolve_invoice_number(validated_data)
        round_off = self._quantize(validated_data.get("round_off", Decimal("0.00")))
        validated_data["round_off"] = round_off

        bill = BranchBill.objects.create(**validated_data)
        line_items, taxable_total, sgst_total, cgst_total = self._build_items(
            bill=bill,
            branch=validated_data["branch"],
            items_data=items_data,
        )
        BranchBillItem.objects.bulk_create(line_items)

        self._recalculate_bill_totals(
            bill=bill,
            taxable_total=taxable_total,
            sgst_total=sgst_total,
            cgst_total=cgst_total,
            round_off=round_off,
        )

        if not self.initial_data.get("invoice_number"):
            party.next_sequence_no += 1
            party.save(update_fields=["next_sequence_no", "updated_at"])

        return bill

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        branch = validated_data.get("branch", instance.branch)
        round_off = self._quantize(validated_data.get("round_off", instance.round_off))
        validated_data["round_off"] = round_off

        if not validated_data.get("invoice_number"):
            validated_data["invoice_number"] = instance.invoice_number

        if items_data is None and branch.id != instance.branch_id:
            raise serializers.ValidationError(
                {"items": "Items are required when changing the branch."}
            )

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            line_items, taxable_total, sgst_total, cgst_total = self._build_items(
                bill=instance,
                branch=branch,
                items_data=items_data,
            )
            instance.items.all().delete()
            BranchBillItem.objects.bulk_create(line_items)
        else:
            taxable_total = instance.taxable_amount
            sgst_total = instance.output_sgst_total
            cgst_total = instance.output_cgst_total

        self._recalculate_bill_totals(
            bill=instance,
            taxable_total=self._quantize(taxable_total),
            sgst_total=self._quantize(sgst_total),
            cgst_total=self._quantize(cgst_total),
            round_off=round_off,
        )

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["branch"] = BranchBillBranchSerializer(instance.branch).data
        data["party"] = BranchBillPartySerializer(instance.party).data
        return data
