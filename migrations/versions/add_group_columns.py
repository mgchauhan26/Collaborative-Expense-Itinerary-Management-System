"""add group columns

Revision ID: add_group_columns
Revises: 7970a7cc5df6
Create Date: 2023-11-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_group_columns'
down_revision = '7970a7cc5df6'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns to group table
    with op.batch_alter_table('group', schema=None) as batch_op:
        batch_op.add_column(sa.Column('join_token', sa.String(length=64)))
        batch_op.add_column(sa.Column('created_at', sa.DateTime()))
        batch_op.add_column(sa.Column('is_active', sa.Boolean()))
    
    # Add column to group_member
    with op.batch_alter_table('group_member', schema=None) as batch_op:
        batch_op.add_column(sa.Column('joined_at', sa.DateTime()))
        batch_op.create_unique_constraint('unique_group_member', ['group_id', 'user_id'])

    # Update nullable columns with default values
    op.execute("UPDATE 'group' SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
    op.execute("UPDATE 'group' SET is_active = 1 WHERE is_active IS NULL")
    op.execute("UPDATE group_member SET joined_at = CURRENT_TIMESTAMP WHERE joined_at IS NULL")
    op.execute("UPDATE 'group' SET join_token = hex(randomblob(32)) WHERE join_token IS NULL")
    
    # Make columns non-nullable
    with op.batch_alter_table('group', schema=None) as batch_op:
        batch_op.alter_column('join_token',
                   existing_type=sa.String(length=64),
                   nullable=False)
        batch_op.alter_column('created_at',
                   existing_type=sa.DateTime(),
                   nullable=False)
        batch_op.alter_column('is_active',
                   existing_type=sa.Boolean(),
                   nullable=False)
        batch_op.create_unique_constraint('uq_group_join_token', ['join_token'])

    with op.batch_alter_table('group_member', schema=None) as batch_op:
        batch_op.alter_column('joined_at',
                   existing_type=sa.DateTime(),
                   nullable=False)


def downgrade():
    with op.batch_alter_table('group_member', schema=None) as batch_op:
        batch_op.drop_constraint('unique_group_member', type_='unique')
        batch_op.drop_column('joined_at')

    with op.batch_alter_table('group', schema=None) as batch_op:
        batch_op.drop_constraint('uq_group_join_token', type_='unique')
        batch_op.drop_column('is_active')
        batch_op.drop_column('created_at')
        batch_op.drop_column('join_token')