"""Anomaly detection and forecasting output models.

Both are organization-scoped and optionally linked to the dataset they
were computed from. `dataset_id` is nullable with `ON DELETE SET NULL` so
that historical anomaly/forecast records are retained even if the source
dataset is later removed.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

ANOMALY_SEVERITIES = ("low", "medium", "high", "critical")


class Anomaly(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        CheckConstraint(f"severity IN {ANOMALY_SEVERITIES}", name="severity_valid"),
        Index("ix_anomalies_org_metric_detected", "organization_id", "metric_name", "detected_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )

    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[Numeric | None] = mapped_column(Numeric(18, 4), nullable=True)
    expected_value: Mapped[Numeric | None] = mapped_column(Numeric(18, 4), nullable=True)


class Forecast(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_org_metric_date", "organization_id", "metric_name", "forecast_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )

    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_value: Mapped[Numeric] = mapped_column(Numeric(18, 4), nullable=False)
    lower_bound: Mapped[Numeric | None] = mapped_column(Numeric(18, 4), nullable=True)
    upper_bound: Mapped[Numeric | None] = mapped_column(Numeric(18, 4), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
