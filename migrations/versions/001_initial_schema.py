"""Create the initial application schema.

Revision ID: 001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return name in inspector.get_table_names(schema="public")


def _upgrade_legacy_schema() -> None:
    """Adopt tables created by the pre-Alembic application without dropping data."""
    op.create_table(
        "app_users",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
        schema="public",
    )
    op.execute(
        sa.text(
            "INSERT INTO public.app_users (user_id) "
            "SELECT user_id FROM public.users_t_invest_tokens "
            "ON CONFLICT (user_id) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO public.app_users (user_id) "
            "SELECT DISTINCT user_id FROM public.user_portfolio "
            "ON CONFLICT (user_id) DO NOTHING"
        )
    )

    op.execute(
        sa.text(
            "UPDATE public.instruments SET currency='RUB' "
            "WHERE currency IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.instruments SET extra_data='{}'::jsonb "
            "WHERE extra_data IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.instruments SET updated_at=now() "
            "WHERE updated_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.user_portfolio SET quantity=0 "
            "WHERE quantity IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.user_portfolio SET paper_data='{}'::jsonb "
            "WHERE paper_data IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.bonds SET extra_data='{}'::jsonb "
            "WHERE extra_data IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE public.user_portfolio AS p SET isin=i.isin "
            "FROM public.instruments AS i "
            "WHERE p.isin=i.secid AND i.isin IS NOT NULL"
        )
    )

    op.alter_column("instruments", "currency", nullable=False, schema="public")
    op.alter_column("instruments", "extra_data", nullable=False, schema="public")
    op.alter_column("instruments", "updated_at", nullable=False, schema="public")
    op.alter_column("user_portfolio", "quantity", nullable=False, schema="public")
    op.alter_column("user_portfolio", "paper_data", nullable=False, schema="public")
    op.alter_column("bonds", "extra_data", nullable=False, schema="public")

    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_instruments_isin') THEN "
            "ALTER TABLE public.instruments ADD CONSTRAINT uq_instruments_isin UNIQUE (isin); "
            "END IF; END $$;"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_tokens_app_user') THEN "
            "ALTER TABLE public.users_t_invest_tokens ADD CONSTRAINT fk_tokens_app_user "
            "FOREIGN KEY (user_id) REFERENCES public.app_users(user_id) ON DELETE CASCADE; "
            "END IF; END $$;"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_portfolio_app_user') THEN "
            "ALTER TABLE public.user_portfolio ADD CONSTRAINT fk_portfolio_app_user "
            "FOREIGN KEY (user_id) REFERENCES public.app_users(user_id) ON DELETE CASCADE; "
            "END IF; END $$;"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_portfolio_instrument') THEN "
            "ALTER TABLE public.user_portfolio ADD CONSTRAINT fk_portfolio_instrument "
            "FOREIGN KEY (isin) REFERENCES public.instruments(isin) ON DELETE RESTRICT NOT VALID; "
            "END IF; END $$;"
        )
    )
    orphan_count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM public.user_portfolio p "
            "LEFT JOIN public.instruments i ON i.isin=p.isin "
            "WHERE i.isin IS NULL"
        )
    ).scalar_one()
    if orphan_count == 0:
        op.execute(
            sa.text(
                "ALTER TABLE public.user_portfolio "
                "VALIDATE CONSTRAINT fk_portfolio_instrument"
            )
        )


def upgrade() -> None:
    if _has_table("instruments"):
        _upgrade_legacy_schema()
        return

    op.create_table(
        "app_users",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
        schema="public",
    )
    op.create_table(
        "instruments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("secid", sa.String(length=30), nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("extra_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secid"),
        sa.UniqueConstraint("isin"),
        schema="public",
    )
    op.create_index(
        "ix_instruments_type", "instruments", ["type"], schema="public"
    )
    op.create_table(
        "users_t_invest_tokens",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_t_invest_token", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["public.app_users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id"),
        schema="public",
    )
    op.create_table(
        "user_portfolio",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("isin", sa.String(length=12), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("avg_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("paper_data", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["isin"], ["public.instruments.isin"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["public.app_users.user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "isin", name="uix_user_isin"),
        schema="public",
    )
    op.create_index(
        "ix_user_portfolio_user_id", "user_portfolio", ["user_id"], schema="public"
    )
    op.create_table(
        "bonds",
        sa.Column("isin", sa.String(length=12), nullable=False),
        sa.Column("extra_data", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("isin"),
        schema="public",
    )


def downgrade() -> None:
    op.drop_table("bonds", schema="public")
    op.drop_index(
        "ix_user_portfolio_user_id", table_name="user_portfolio", schema="public"
    )
    op.drop_table("user_portfolio", schema="public")
    op.drop_table("users_t_invest_tokens", schema="public")
    op.drop_index("ix_instruments_type", table_name="instruments", schema="public")
    op.drop_table("instruments", schema="public")
    op.drop_table("app_users", schema="public")
