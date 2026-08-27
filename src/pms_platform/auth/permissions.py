"""Application permission codes for business vs operational access."""

from __future__ import annotations

PERMISSION_VIEW_APPROVED = "view_approved_data"
PERMISSION_CREATE_DRAFT = "create_draft_changes"
PERMISSION_SUBMIT = "submit_changes"
PERMISSION_WITHDRAW_OWN = "withdraw_own_changes"
PERMISSION_VIEW_OWN_WORKING = "view_own_working_data"
PERMISSION_VIEW_ALL_SUBMITTED = "view_all_submitted_changes"
PERMISSION_PREVIEW_SUBMITTED = "preview_submitted_changes"
PERMISSION_APPROVE_BUSINESS = "approve_business_changes"
PERMISSION_REJECT_BUSINESS = "reject_business_changes"
PERMISSION_MANAGE_USERS = "manage_operational_users"
PERMISSION_VIEW_DIAGNOSTICS = "view_system_diagnostics"

ALL_PERMISSIONS = frozenset(
    {
        PERMISSION_VIEW_APPROVED,
        PERMISSION_CREATE_DRAFT,
        PERMISSION_SUBMIT,
        PERMISSION_WITHDRAW_OWN,
        PERMISSION_VIEW_OWN_WORKING,
        PERMISSION_VIEW_ALL_SUBMITTED,
        PERMISSION_PREVIEW_SUBMITTED,
        PERMISSION_APPROVE_BUSINESS,
        PERMISSION_REJECT_BUSINESS,
        PERMISSION_MANAGE_USERS,
        PERMISSION_VIEW_DIAGNOSTICS,
    }
)

ROLE_DEFAULT_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSIONS,
    "client": frozenset(
        {
            PERMISSION_VIEW_APPROVED,
            PERMISSION_CREATE_DRAFT,
            PERMISSION_SUBMIT,
            PERMISSION_WITHDRAW_OWN,
            PERMISSION_VIEW_OWN_WORKING,
        }
    ),
    "member": frozenset(
        {
            PERMISSION_VIEW_APPROVED,
            PERMISSION_CREATE_DRAFT,
            PERMISSION_SUBMIT,
            PERMISSION_WITHDRAW_OWN,
            PERMISSION_VIEW_OWN_WORKING,
            PERMISSION_VIEW_DIAGNOSTICS,
        }
    ),
}
