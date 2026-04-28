"""sync users and audit schema

Revision ID: b7f1c2d9a4ef
Revises: fa43e03856d6
Create Date: 2026-04-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7f1c2d9a4ef"
down_revision: Union[str, Sequence[str], None] = "fa43e03856d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if "users" not in table_names:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("credits", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    else:
        user_columns = {column["name"] for column in inspector.get_columns("users")}

        if "hashed_password" not in user_columns:
            op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=True))
        if "full_name" not in user_columns:
            op.add_column("users", sa.Column("full_name", sa.String(length=255), nullable=True))
        if "credits" not in user_columns:
            op.add_column("users", sa.Column("credits", sa.Integer(), nullable=False, server_default="10"))
        if "role" not in user_columns:
            op.add_column("users", sa.Column("role", sa.String(length=50), nullable=False, server_default="user"))
        if "is_active" not in user_columns:
            op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "created_at" not in user_columns:
            op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))

        user_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
        if op.f("ix_users_id") not in user_indexes:
            op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
        if op.f("ix_users_email") not in user_indexes:
            op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    if "audit_logs" not in table_names:
        return

    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}

    if "user_id" not in audit_columns:
        op.add_column("audit_logs", sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)
        op.create_foreign_key(
            "fk_audit_logs_user_id_users",
            "audit_logs",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "audit_logs" in table_names:
        audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    else:
        audit_columns = set()

    if "user_id" in audit_columns and "audit_logs" in table_names:
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("audit_logs") if fk.get("name")}
        if "fk_audit_logs_user_id_users" in fk_names:
            op.drop_constraint("fk_audit_logs_user_id_users", "audit_logs", type_="foreignkey")

        index_names = {idx["name"] for idx in inspector.get_indexes("audit_logs")}
        if op.f("ix_audit_logs_user_id") in index_names:
            op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")

        op.drop_column("audit_logs", "user_id")

    if "users" in table_names:
        index_names = {idx["name"] for idx in inspector.get_indexes("users")}
        if op.f("ix_users_email") in index_names:
            op.drop_index(op.f("ix_users_email"), table_name="users")
        if op.f("ix_users_id") in index_names:
            op.drop_index(op.f("ix_users_id"), table_name="users")
        op.drop_table("users")
