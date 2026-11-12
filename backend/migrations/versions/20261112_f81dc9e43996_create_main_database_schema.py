"""Create the Main Database schema (ON-11)

The six tables the Interface Contracts name: users, documents, sections,
chat logs, feedback and escalations.

Enumerated columns are VARCHAR with a check constraint rather than a
PostgreSQL enum type, so the same migration runs on the SQLite the unit
tests use. Deleting a document takes its sections with it, because a
section whose document was removed would still be cited; everything that
points at a user is RESTRICT, so a user cannot be deleted out from under
the chat history that references them.

Revision ID: f81dc9e43996
Revises:
Created: 2026-11-12 00:00:54.234614+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f81dc9e43996"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "employee",
                "hr_administrator",
                name="user_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "chat_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("fallback", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_chat_logs_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_logs")),
    )
    op.create_index(op.f("ix_chat_logs_user_id"), "chat_logs", ["user_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "content_type",
            sa.Enum("pdf", "txt", name="document_type", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name=op.f("fk_documents_uploaded_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(
        op.f("ix_documents_uploaded_by_id"), "documents", ["uploaded_by_id"], unique=False
    )
    op.create_table(
        "escalations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_log_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "resolved",
                name="escalation_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("hr_reply", sa.Text(), nullable=True),
        sa.Column("resolved_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["chat_log_id"],
            ["chat_logs.id"],
            name=op.f("fk_escalations_chat_log_id_chat_logs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            name=op.f("fk_escalations_resolved_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_escalations_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalations")),
    )
    op.create_index(
        op.f("ix_escalations_chat_log_id"), "escalations", ["chat_log_id"], unique=False
    )
    op.create_index(op.f("ix_escalations_status"), "escalations", ["status"], unique=False)
    op.create_index(op.f("ix_escalations_user_id"), "escalations", ["user_id"], unique=False)
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_log_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "rating",
            sa.Enum(
                "up", "down", name="feedback_rating", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_log_id"],
            ["chat_logs.id"],
            name=op.f("fk_feedback_chat_log_id_chat_logs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        sa.UniqueConstraint("chat_log_id", "user_id", name="one_rating_per_user"),
    )
    op.create_index(op.f("ix_feedback_chat_log_id"), "feedback", ["chat_log_id"], unique=False)
    op.create_index(op.f("ix_feedback_user_id"), "feedback", ["user_id"], unique=False)
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_sections_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("document_id", "position", name="document_position"),
    )
    op.create_index(op.f("ix_sections_document_id"), "sections", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sections_document_id"), table_name="sections")
    op.drop_table("sections")
    op.drop_index(op.f("ix_feedback_user_id"), table_name="feedback")
    op.drop_index(op.f("ix_feedback_chat_log_id"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_index(op.f("ix_escalations_user_id"), table_name="escalations")
    op.drop_index(op.f("ix_escalations_status"), table_name="escalations")
    op.drop_index(op.f("ix_escalations_chat_log_id"), table_name="escalations")
    op.drop_table("escalations")
    op.drop_index(op.f("ix_documents_uploaded_by_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_chat_logs_user_id"), table_name="chat_logs")
    op.drop_table("chat_logs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
