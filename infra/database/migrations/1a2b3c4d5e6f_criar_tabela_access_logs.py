"""Criar tabela access_logs

Revision ID: 1a2b3c4d5e6f
Revises:
Create Date: 2024-01-22 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# Identificadores da revisão (gerados automaticamente pelo Alembic)
revision = '1a2b3c4d5e6f'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # 1. Criação da Tabela
    op.create_table(
        'access_logs',
        sa.Column('id', sa.Integer(), sa.Identity(always=True), nullable=False),
        sa.Column('device_sn', sa.String(length=50), nullable=False),
        sa.Column('enroll_id', sa.Integer(), nullable=False),
        sa.Column('user_name', sa.String(length=100), nullable=True),
        sa.Column('event_time', sa.DateTime(), nullable=False),
        sa.Column('mode', sa.Integer(), nullable=True),
        sa.Column('inout_mode', sa.Integer(), nullable=True),
        sa.Column('event_code', sa.Integer(), nullable=True),
        sa.Column('image_base64', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. Criação dos Índices
    op.create_index('idx_device_sn', 'access_logs', ['device_sn'], unique=False)
    op.create_index('idx_event_time', 'access_logs', ['event_time'], unique=False)


def downgrade():
    # Remove a tabela e os índices (o Postgres remove os índices automaticamente ao dropar a tabela)
    op.drop_table('access_logs')
