"""Add dispositivos table

Revision ID: 3a4b5c6d7e8f
Revises: 2a3b4c5d6e7f
Create Date: 2024-05-23 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# Identificadores da revisão
revision = '3a4b5c6d7e8f'
down_revision = '2a3b4c5d6e7f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'dispositivos',
        sa.Column('sn', sa.String(length=50), primary_key=True),
        sa.Column('last_communication', sa.DateTime(), nullable=False)
    )

def downgrade():
    op.drop_table('dispositivos')
