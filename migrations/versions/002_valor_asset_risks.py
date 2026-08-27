"""Create and seed the Valor expert risk catalog.

Revision ID: 002_valor_asset_risks
Revises: 001_initial_schema
"""

from alembic import op
import sqlalchemy as sa

from app.database.valor_seed import VALOR_ASSET_RISKS


revision = "002_valor_asset_risks"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


RISK_COLUMNS = (
    "inflation_risk",
    "geopolitical_risk",
    "domestic_political_risk",
    "debt_risk",
    "currency_risk",
    "minority_shareholder_risk",
)


def upgrade() -> None:
    op.create_table(
        "valor_asset_risks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("asset_type", sa.String(length=10), nullable=False),
        sa.Column("identifier", sa.String(length=30), nullable=False),
        sa.Column("issuer", sa.String(length=120), nullable=False),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column("company_type", sa.String(length=50), nullable=True),
        sa.Column("bond_kind", sa.String(length=20), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("coupon_type", sa.String(length=30), nullable=True),
        *(
            sa.Column(column, sa.SmallInteger(), nullable=True)
            for column in RISK_COLUMNS
        ),
        sa.Column("source_sheet", sa.String(length=50), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "asset_type IN ('share', 'bond')", name="ck_valor_asset_type"
        ),
        *(
            sa.CheckConstraint(
                f"{column} BETWEEN 1 AND 6", name=f"ck_valor_{column}"
            )
            for column in RISK_COLUMNS
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_type", "identifier", name="uq_valor_asset_type_identifier"
        ),
        schema="public",
    )
    op.create_index(
        "ix_valor_asset_risks_asset_type",
        "valor_asset_risks",
        ["asset_type"],
        schema="public",
    )
    op.create_index(
        "ix_valor_asset_risks_identifier",
        "valor_asset_risks",
        ["identifier"],
        schema="public",
    )

    seed_table = sa.table(
        "valor_asset_risks",
        sa.column("asset_type", sa.String),
        sa.column("identifier", sa.String),
        sa.column("issuer", sa.String),
        sa.column("sector", sa.String),
        sa.column("company_type", sa.String),
        sa.column("bond_kind", sa.String),
        sa.column("currency", sa.String),
        sa.column("coupon_type", sa.String),
        *(sa.column(column, sa.SmallInteger) for column in RISK_COLUMNS),
        sa.column("source_sheet", sa.String),
        schema="public",
    )
    op.bulk_insert(seed_table, VALOR_ASSET_RISKS)


def downgrade() -> None:
    op.drop_index(
        "ix_valor_asset_risks_identifier",
        table_name="valor_asset_risks",
        schema="public",
    )
    op.drop_index(
        "ix_valor_asset_risks_asset_type",
        table_name="valor_asset_risks",
        schema="public",
    )
    op.drop_table("valor_asset_risks", schema="public")
