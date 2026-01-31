"""Add manual fields to registros

Revision ID: 2a3b4c5d6e7f
Revises: 1a2b3c4d5e6f
Create Date: 2024-05-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# Identificadores da revisão
revision = '2a3b4c5d6e7f'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None

def upgrade():
    # 1. Garantir que a tabela registros exista (caso não tenha sido criada por migração anterior)
    op.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY,
            func_id TEXT NOT NULL,
            horario TIMESTAMP NOT NULL
        )
    """)

    # 2. Adicionar as novas colunas
    # Nota: Usamos server_default para registros existentes
    op.add_column('registros', sa.Column('origem', sa.String(length=20), server_default='equipamento', nullable=False))
    op.add_column('registros', sa.Column('justificativa', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('registros', 'justificativa')
    op.drop_column('registros', 'origem')
