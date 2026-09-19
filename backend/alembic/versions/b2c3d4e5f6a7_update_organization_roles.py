"""update organization roles to canonical 4-role model

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate any legacy data in organization_members:
    #    owner -> admin
    #    member -> analyst
    op.execute("UPDATE organization_members SET role = 'admin' WHERE role = 'owner'")
    op.execute("UPDATE organization_members SET role = 'analyst' WHERE role = 'member'")

    # 2. Drop the old check constraint allowing ('owner', 'admin', 'member', 'viewer')
    op.drop_constraint(
        op.f('ck_organization_members_role_valid'),
        'organization_members',
        type_='check',
    )

    # 3. Create the new check constraint strictly allowing ('admin', 'analyst', 'manager', 'viewer')
    op.create_check_constraint(
        op.f('ck_organization_members_role_valid'),
        'organization_members',
        "role IN ('admin', 'analyst', 'manager', 'viewer')",
    )


def downgrade() -> None:
    # 1. Drop the 4-role check constraint
    op.drop_constraint(
        op.f('ck_organization_members_role_valid'),
        'organization_members',
        type_='check',
    )

    # 2. Map analyst back to member for downgrade
    op.execute("UPDATE organization_members SET role = 'member' WHERE role = 'analyst'")

    # 3. Restore the legacy check constraint
    op.create_check_constraint(
        op.f('ck_organization_members_role_valid'),
        'organization_members',
        "role IN ('owner', 'admin', 'member', 'viewer')",
    )
