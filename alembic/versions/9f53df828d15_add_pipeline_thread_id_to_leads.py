"""add_pipeline_thread_id_to_leads

Revision ID: 9f53df828d15
Revises: 
Create Date: 2026-07-15 19:26:50.569561

NOTE: pipeline_thread_id and scores.reasons were partially applied
by the first migration attempt. This migration handles remaining work
and is safe to re-run (uses IF NOT EXISTS / IF EXISTS guards via
conditional logic).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '9f53df828d15'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    conn = op.get_bind()

    # Add pipeline_thread_id if not already present
    if not _column_exists(conn, 'leads', 'pipeline_thread_id'):
        op.add_column('leads', sa.Column('pipeline_thread_id', sa.String(length=64), nullable=True))

    # Create index if not already present (SQLite allows this)
    with op.batch_alter_table('leads') as batch_op:
        try:
            batch_op.create_index('ix_leads_pipeline_thread_id', ['pipeline_thread_id'], unique=False)
        except Exception:
            pass  # Index already exists

    # Add reasons column if not already present
    if not _column_exists(conn, 'scores', 'reasons'):
        op.add_column('scores', sa.Column('reasons', sqlite.JSON(), nullable=True))

    # Drop old 'reason' column if it still exists
    if _column_exists(conn, 'scores', 'reason'):
        with op.batch_alter_table('scores') as batch_op:
            batch_op.drop_column('reason')


def downgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, 'scores', 'reason'):
        with op.batch_alter_table('scores') as batch_op:
            batch_op.add_column(sa.Column('reason', sa.TEXT(), nullable=True))

    if _column_exists(conn, 'scores', 'reasons'):
        with op.batch_alter_table('scores') as batch_op:
            batch_op.drop_column('reasons')

    try:
        op.drop_index('ix_leads_pipeline_thread_id', table_name='leads')
    except Exception:
        pass

    if _column_exists(conn, 'leads', 'pipeline_thread_id'):
        with op.batch_alter_table('leads') as batch_op:
            batch_op.drop_column('pipeline_thread_id')
