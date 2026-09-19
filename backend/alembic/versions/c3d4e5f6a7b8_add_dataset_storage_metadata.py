"""add dataset storage metadata and update statuses

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-19 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add storage metadata columns to datasets
    op.add_column(
        'datasets',
        sa.Column('storage_path', sa.String(length=1024), nullable=False, server_default=''),
    )
    op.add_column(
        'datasets',
        sa.Column('file_type', sa.String(length=16), nullable=False, server_default='csv'),
    )
    op.add_column(
        'datasets',
        sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'),
    )

    # 2. Update status check constraint to strictly allow: uploaded, processing, ready, failed
    op.drop_constraint(op.f('ck_datasets_status_valid'), 'datasets', type_='check')
    op.create_check_constraint(
        op.f('ck_datasets_status_valid'),
        'datasets',
        "status IN ('uploaded', 'processing', 'ready', 'failed')",
    )


def downgrade() -> None:
    # 1. Restore old status check constraint
    op.drop_constraint(op.f('ck_datasets_status_valid'), 'datasets', type_='check')
    op.create_check_constraint(
        op.f('ck_datasets_status_valid'),
        'datasets',
        "status IN ('uploaded', 'profiling', 'ready', 'error')",
    )

    # 2. Drop added columns
    op.drop_column('datasets', 'file_size')
    op.drop_column('datasets', 'file_type')
    op.drop_column('datasets', 'storage_path')
