"""Sessions and agent conversations tables

Revision ID: 0003_sessions_agent
Revises: 0002_movielens
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_sessions_agent"
down_revision = "20260405_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("movie_interactions", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("messages", sa.Text, nullable=True),
        sa.Column("extracted_preferences", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_conversations")
    op.drop_table("user_sessions")
