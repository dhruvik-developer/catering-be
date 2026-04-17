from django.contrib import admin

from .models import BranchBankDetails, BranchFormat, PartyInformation


@admin.register(BranchFormat)
class BranchFormatAdmin(admin.ModelAdmin):
    list_display = ("branch_name", "branch_code", "gst_number", "is_active")
    search_fields = ("branch_name", "branch_code", "gst_number")
    list_filter = ("is_active",)


@admin.register(BranchBankDetails)
class BranchBankDetailsAdmin(admin.ModelAdmin):
    list_display = ("branch", "bank_name", "account_number", "ifsc_code")
    search_fields = (
        "branch__branch_name",
        "branch__branch_code",
        "bank_name",
        "account_number",
        "ifsc_code",
    )


@admin.register(PartyInformation)
class PartyInformationAdmin(admin.ModelAdmin):
    list_display = (
        "party_name",
        "party_code",
        "party_gst_no",
        "invoice_prefix",
        "next_sequence_no",
        "is_active",
    )
    search_fields = ("party_name", "party_code", "party_gst_no", "invoice_prefix")
    list_filter = ("is_active",)
