"""ORM models package.

Every model must be imported here so that `Base.metadata` is fully
populated when Alembic's `--autogenerate` inspects it (see
alembic/env.py). Importing a model module solely for its side effect of
registering the class with `Base` is intentional — the `noqa: F401` marks
suppress "unused import" warnings for exactly that reason.
"""

from app.db.base import Base  # noqa: F401
from app.db.models.ai import AIConversation, AIMessage, AnalyticsQuery  # noqa: F401
from app.db.models.audit import AuditLog  # noqa: F401
from app.db.models.crm import Customer, Order, Payment, Product  # noqa: F401
from app.db.models.dataset import Dataset, DatasetColumn  # noqa: F401
from app.db.models.document import Document, DocumentChunk  # noqa: F401
from app.db.models.ml import Anomaly, Forecast  # noqa: F401
from app.db.models.organization import Organization, OrganizationMember  # noqa: F401
from app.db.models.report import Report  # noqa: F401
from app.db.models.user import User  # noqa: F401

__all__ = [
    "Base",
    "Organization",
    "OrganizationMember",
    "User",
    "Dataset",
    "DatasetColumn",
    "Customer",
    "Product",
    "Order",
    "Payment",
    "Document",
    "DocumentChunk",
    "AnalyticsQuery",
    "AIConversation",
    "AIMessage",
    "Anomaly",
    "Forecast",
    "Report",
    "AuditLog",
]
