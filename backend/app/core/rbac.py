"""
core/rbac.py
============
Role-Based Access Control (RBAC) definitions and permissions for InsightForge AI.

The platform recognizes exactly four canonical roles:
  * ADMIN: Full organization administration, member/role management, resource management.
  * ANALYST: Dataset upload, profiling, cleaning, analytics execution, AI tools, reports.
  * MANAGER: Read-only dashboards, analytics, reports, business intelligence features.
  * VIEWER: Strict read-only access to permitted dashboards, analytics, and reports.
"""

from __future__ import annotations

from enum import Enum


class RoleEnum(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    MANAGER = "manager"
    VIEWER = "viewer"


CANONICAL_ROLES = tuple(r.value for r in RoleEnum)

# Granular permission strings
PERM_ORG_MANAGE = "org:manage"
PERM_MEMBERS_MANAGE = "members:manage"
PERM_DATA_MUTATE = "data:mutate"
PERM_ANALYTICS_RUN = "analytics:run"
PERM_REPORTS_GENERATE = "reports:generate"
PERM_DASHBOARD_READ = "dashboard:read"
PERM_REPORTS_READ = "reports:read"

# Explicit role-to-permissions mapping
ROLE_PERMISSIONS: dict[str, set[str]] = {
    RoleEnum.ADMIN.value: {
        PERM_ORG_MANAGE,
        PERM_MEMBERS_MANAGE,
        PERM_DATA_MUTATE,
        PERM_ANALYTICS_RUN,
        PERM_REPORTS_GENERATE,
        PERM_DASHBOARD_READ,
        PERM_REPORTS_READ,
    },
    RoleEnum.ANALYST.value: {
        PERM_DATA_MUTATE,
        PERM_ANALYTICS_RUN,
        PERM_REPORTS_GENERATE,
        PERM_DASHBOARD_READ,
        PERM_REPORTS_READ,
    },
    RoleEnum.MANAGER.value: {
        PERM_DASHBOARD_READ,
        PERM_REPORTS_READ,
    },
    RoleEnum.VIEWER.value: {
        PERM_DASHBOARD_READ,
        PERM_REPORTS_READ,
    },
}


def normalize_role(role: str) -> str:
    """Normalize and validate a role string.

    Converts to lowercase (e.g. 'ADMIN' -> 'admin') and validates against
    canonical roles. Raises ValueError if invalid.
    """
    if not isinstance(role, str):
        raise ValueError(f"Role must be a string, got {type(role)}")
    clean = role.strip().lower()
    if clean not in CANONICAL_ROLES:
        valid_display = ", ".join(r.upper() for r in RoleEnum)
        raise ValueError(f"Invalid role '{role}'. Allowed roles are: {valid_display}")
    return clean


def has_permission(role: str, permission: str) -> bool:
    """Return True if *role* possesses *permission*."""
    try:
        norm = normalize_role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(norm, set())


def can_manage_members(role: str) -> bool:
    """Return True if *role* can manage organization members."""
    return has_permission(role, PERM_MEMBERS_MANAGE)


def can_mutate_data(role: str) -> bool:
    """Return True if *role* can upload, profile, clean, or mutate datasets."""
    return has_permission(role, PERM_DATA_MUTATE)
