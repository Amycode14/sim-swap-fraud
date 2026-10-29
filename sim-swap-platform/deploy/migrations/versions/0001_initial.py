"""Initial tenant and JSON record storage. Explicit migration for non-demo environments."""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('tenants',sa.Column('id',sa.String(80),primary_key=True))
    op.create_table('records',sa.Column('id',sa.String(36),primary_key=True),
                    sa.Column('tenant',sa.String(80),nullable=False),sa.Column('kind',sa.String(30),nullable=False),
                    sa.Column('key',sa.String(128),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
                    sa.Column('created',sa.String(40),nullable=False),sa.Column('body',sa.Text(),nullable=False),
                    sa.UniqueConstraint('tenant','kind','key'))
    op.create_index('record_lookup','records',['tenant','kind','created'])


def downgrade():
    raise RuntimeError('Destructive schema downgrade is disabled; restore an approved backup instead')
