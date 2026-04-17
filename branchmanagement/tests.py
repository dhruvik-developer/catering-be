from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from .models import (
    BranchFormat,
    PartyInformation,
    BranchItem,
    BranchBill,
    BranchBankDetails,
)
from .serializers import BranchFormatSerializer, PartyInformationSerializer, BranchBillSerializer


class BranchFormatModelTests(TestCase):
    def test_invalid_gst_number_raises_validation_error(self):
        branch = BranchFormat(
            branch_name="Main Branch",
            address="Surat",
            gst_number="24ALVPA0722H1ZE",
        )

        branch.gst_number = "INVALIDGST"
        with self.assertRaises(ValidationError):
            branch.full_clean()

    def test_branch_code_is_generated_when_blank(self):
        branch = BranchFormat.objects.create(
            branch_name="Main Branch",
            address="Surat",
            gst_number="24ALVPA0722H1ZE",
        )

        self.assertEqual(branch.branch_code, f"BR{1000 + branch.pk}")
        self.assertEqual(
            branch.display_name,
            f"Main Branch ({branch.branch_code})",
        )


class BranchFormatSerializerTests(TestCase):
    def test_serializer_normalizes_prefix_and_gst(self):
        serializer = BranchFormatSerializer(
            data={
                "branch_name": " Mayur Bhajiya ",
                "address": " Umarvada, Surat ",
                "gst_number": "24alvpa0722h1ze",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["branch_name"], "Mayur Bhajiya")
        self.assertEqual(serializer.validated_data["address"], "Umarvada, Surat")
        self.assertEqual(serializer.validated_data["gst_number"], "24ALVPA0722H1ZE")

    def test_serializer_saves_nested_bank_details(self):
        serializer = BranchFormatSerializer(
            data={
                "branch_name": " Main Branch ",
                "address": " Surat ",
                "bank_details": {
                    "bank_name": " Bank of Baroda ",
                    "account_number": " 123456789 ",
                    "ifsc_code": " barb0vjapun ",
                    "account_holder_name": " John Doe ",
                },
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        branch = serializer.save()

        self.assertEqual(branch.bank_details.bank_name, "Bank of Baroda")
        self.assertEqual(branch.bank_details.account_number, "123456789")
        self.assertEqual(branch.bank_details.ifsc_code, "BARB0VJAPUN")
        self.assertEqual(branch.bank_details.account_holder_name, "John Doe")


class PartyInformationModelTests(TestCase):
    def test_party_code_is_generated_when_blank(self):
        party = PartyInformation.objects.create(
            party_name="MS SMIMER MEDICAL COLLEGE SMC",
            party_gst_no="24AAALS0678Q1ZE",
            invoice_prefix="SMC-",
            next_sequence_no=163,
        )

        self.assertEqual(party.party_code, str(1000 + party.pk))
        self.assertEqual(party.next_invoice_preview, "SMC-163")


class PartyInformationSerializerTests(TestCase):
    def test_serializer_normalizes_party_information(self):
        serializer = PartyInformationSerializer(
            data={
                "party_name": " MS SMIMER MEDICAL COLLEGE SMC ",
                "party_gst_no": "24aaals0678q1ze",
                "party_code": " 1522 ",
                "invoice_prefix": " smc- ",
                "next_sequence_no": 163,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["party_name"], "MS SMIMER MEDICAL COLLEGE SMC"
        )
        self.assertEqual(serializer.validated_data["party_gst_no"], "24AAALS0678Q1ZE")
        self.assertEqual(serializer.validated_data["party_code"], "1522")
        self.assertEqual(serializer.validated_data["invoice_prefix"], "SMC-")


class BranchBillSerializerTests(TestCase):
    def setUp(self):
        self.branch = BranchFormat.objects.create(
            branch_name="Civil Branch",
            address="Surat",
            gst_number="24ALVPA0722H1ZE",
        )
        BranchBankDetails.objects.create(
            branch=self.branch,
            bank_name="db",
            account_number="1234574321",
            ifsc_code="VBHT5GFGGF",
            account_holder_name="bbb",
        )
        self.party = PartyInformation.objects.create(
            party_name="Government Medical College",
            party_gst_no="24AAALS0678Q1ZE",
            party_code="SDD",
            invoice_prefix="WER26-",
            next_sequence_no=2,
        )
        self.branch_item = BranchItem.objects.create(
            branch=self.branch,
            name="LIMBOO SARBAT300ML",
            rate=Decimal("30.00"),
        )

    def test_serializer_creates_bill_and_computes_totals(self):
        serializer = BranchBillSerializer(
            data={
                "branch": self.branch.id,
                "party": self.party.id,
                "invoice_date": "2026-04-13",
                "order_number": "N/A",
                "hsn_code": "996331",
                "refrance": "2026-04-01 to 2026-04-30",
                "round_off": "0.00",
                "items": [
                    {
                        "branch_item": self.branch_item.id,
                        "quantity": "2",
                        "gst_percentage": "5",
                    }
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        bill = serializer.save()

        self.assertEqual(bill.invoice_number, "WER26-2")
        self.assertEqual(bill.taxable_amount, Decimal("60.00"))
        self.assertEqual(bill.output_sgst_total, Decimal("1.50"))
        self.assertEqual(bill.output_cgst_total, Decimal("1.50"))
        self.assertEqual(bill.final_payable_amount, Decimal("63.00"))
        self.assertEqual(bill.items.count(), 1)

        self.party.refresh_from_db()
        self.assertEqual(self.party.next_sequence_no, 3)

    def test_serializer_representation_returns_nested_branch_and_party(self):
        bill = BranchBill.objects.create(
            branch=self.branch,
            party=self.party,
            invoice_number="WER26-2",
            invoice_date="2026-04-13",
            order_number="001",
            hsn_code="996331",
            refrance="2026-04-01 to 2026-04-30",
            taxable_amount=Decimal("60.00"),
            output_sgst_total=Decimal("1.50"),
            output_cgst_total=Decimal("1.50"),
            round_off=Decimal("0.00"),
            final_payable_amount=Decimal("63.00"),
            notes="pay before month end",
        )

        serializer = BranchBillSerializer(instance=bill)

        self.assertEqual(serializer.data["refrance"], "2026-04-01 to 2026-04-30")
        self.assertEqual(serializer.data["branch"]["id"], self.branch.id)
        self.assertEqual(serializer.data["branch"]["display_name"], self.branch.display_name)
        self.assertEqual(serializer.data["branch"]["bank_details"]["bank_name"], "db")
        self.assertEqual(serializer.data["party"]["id"], self.party.id)
        self.assertEqual(serializer.data["party"]["party_code"], "SDD")
        self.assertEqual(serializer.data["party"]["next_invoice_preview"], "WER26-2")

    def test_serializer_creates_bill_with_inclusive_rate(self):
        serializer = BranchBillSerializer(
            data={
                "branch": self.branch.id,
                "party": self.party.id,
                "invoice_date": "2026-04-13",
                "round_off": "0.00",
                "items": [
                    {
                        "branch_item": self.branch_item.id,
                        "quantity": "1",
                        "rate": "105.00",
                        "gst_percentage": "5",
                        "is_rate_inclusive": True,
                    }
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        bill = serializer.save()
        item = bill.items.get()

        self.assertEqual(item.is_rate_inclusive, True)
        self.assertEqual(item.taxable_amount, Decimal("100.00"))
        self.assertEqual(item.sgst_amount, Decimal("2.50"))
        self.assertEqual(item.cgst_amount, Decimal("2.50"))
        self.assertEqual(item.amount, Decimal("105.00"))
        self.assertEqual(bill.taxable_amount, Decimal("100.00"))
        self.assertEqual(bill.output_sgst_total, Decimal("2.50"))
        self.assertEqual(bill.output_cgst_total, Decimal("2.50"))
        self.assertEqual(bill.final_payable_amount, Decimal("105.00"))


class BranchBillAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="admin",
            password="pass123",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

        self.branch = BranchFormat.objects.create(
            branch_name="Civil Branch",
            address="Surat",
            gst_number="24ALVPA0722H1ZE",
        )
        BranchBankDetails.objects.create(
            branch=self.branch,
            bank_name="db",
            account_number="1234574321",
            ifsc_code="VBHT5GFGGF",
            account_holder_name="bbb",
        )
        self.party = PartyInformation.objects.create(
            party_name="Government Medical College",
            party_gst_no="24AAALS0678Q1ZE",
            party_code="SDD",
            invoice_prefix="WER26-",
            next_sequence_no=10,
        )
        self.branch_item = BranchItem.objects.create(
            branch=self.branch,
            name="FULL LUNCH PLATE FOR STUDENTS",
            rate=Decimal("200.00"),
        )

    def test_create_and_fetch_branch_bill(self):
        create_response = self.client.post(
            "/api/branch-bills/",
            {
                "branch": self.branch.id,
                "party": self.party.id,
                "invoice_date": "2026-04-13",
                "order_number": "N/A",
                "hsn_code": "996331",
                "refrance": "2026-04-01 to 2026-04-30",
                "round_off": "0.00",
                "items": [
                    {
                        "branch_item": self.branch_item.id,
                        "quantity": "1",
                        "gst_percentage": "5",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        self.assertTrue(create_response.data["status"])
        self.assertEqual(
            create_response.data["data"]["final_payable_amount"], "210.00"
        )

        bill_id = create_response.data["data"]["id"]
        fetch_response = self.client.get(f"/api/branch-bills/{bill_id}/")

        self.assertEqual(fetch_response.status_code, 200, fetch_response.data)
        self.assertTrue(fetch_response.data["status"])
        self.assertEqual(fetch_response.data["data"]["items"][0]["item_name"], self.branch_item.name)
        self.assertEqual(fetch_response.data["data"]["invoice_number"], "WER26-10")
        self.assertEqual(
            fetch_response.data["data"]["refrance"],
            "2026-04-01 to 2026-04-30",
        )
        self.assertEqual(fetch_response.data["data"]["branch"]["id"], self.branch.id)
        self.assertEqual(
            fetch_response.data["data"]["branch"]["display_name"],
            self.branch.display_name,
        )
        self.assertEqual(
            fetch_response.data["data"]["branch"]["bank_details"]["account_number"],
            "1234574321",
        )
        self.assertEqual(fetch_response.data["data"]["party"]["id"], self.party.id)
        self.assertEqual(fetch_response.data["data"]["party"]["party_code"], "SDD")
        self.assertEqual(
            fetch_response.data["data"]["party"]["next_invoice_preview"],
            "WER26-11",
        )

        self.assertEqual(BranchBill.objects.count(), 1)

    def test_put_updates_branch_bill_and_recalculates_items(self):
        create_response = self.client.post(
            "/api/branch-bills/",
            {
                "branch": self.branch.id,
                "party": self.party.id,
                "invoice_date": "2026-04-13",
                "order_number": "N/A",
                "hsn_code": "996331",
                "refrance": "2026-04-01 to 2026-04-30",
                "round_off": "0.00",
                "items": [
                    {
                        "branch_item": self.branch_item.id,
                        "quantity": "1",
                        "gst_percentage": "5",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, 201, create_response.data)
        bill_id = create_response.data["data"]["id"]

        update_response = self.client.put(
            f"/api/branch-bills/{bill_id}/",
            {
                "branch": self.branch.id,
                "party": self.party.id,
                "invoice_number": "WER26-UPDATED",
                "invoice_date": "2026-04-15",
                "order_number": "ORD-2",
                "hsn_code": "996331",
                "refrance": "2026-04-15",
                "round_off": "0.00",
                "notes": "updated",
                "items": [
                    {
                        "branch_item": self.branch_item.id,
                        "quantity": "2",
                        "rate": "210.00",
                        "gst_percentage": "5",
                        "is_rate_inclusive": True,
                        "sort_order": 1,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, 200, update_response.data)
        self.assertTrue(update_response.data["status"])
        self.assertEqual(
            update_response.data["data"]["invoice_number"],
            "WER26-UPDATED",
        )
        self.assertEqual(
            update_response.data["data"]["items"][0]["is_rate_inclusive"],
            True,
        )
        self.assertEqual(
            update_response.data["data"]["items"][0]["taxable_amount"],
            "400.00",
        )
        self.assertEqual(update_response.data["data"]["items"][0]["amount"], "420.00")
        self.assertEqual(update_response.data["data"]["final_payable_amount"], "420.00")

        bill = BranchBill.objects.get(pk=bill_id)
        item = bill.items.get()
        self.assertEqual(item.is_rate_inclusive, True)
        self.assertEqual(item.taxable_amount, Decimal("400.00"))
        self.assertEqual(item.amount, Decimal("420.00"))
