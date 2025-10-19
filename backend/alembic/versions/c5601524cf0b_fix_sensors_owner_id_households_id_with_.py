from alembic import op
import sqlalchemy as sa

revision = "c5601524cf0b"
down_revision = "d4e495954bc5"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "sensors" in tables:
        cols = {c["name"] for c in insp.get_columns("sensors")}
        if "new_owner_id" not in cols:
            op.add_column("sensors", sa.Column("new_owner_id", sa.Integer(), nullable=True))

    if "households" in tables:
        cols = {c["name"] for c in insp.get_columns("households")}
        if "new_house_id" not in cols:
            op.add_column("households", sa.Column("new_house_id", sa.Integer(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "sensors" in tables:
        cols = {c["name"] for c in insp.get_columns("sensors")}
        if "new_owner_id" in cols:
            op.drop_column("sensors", "new_owner_id")

    if "households" in tables:
        cols = {c["name"] for c in insp.get_columns("households")}
        if "new_house_id" in cols:
            op.drop_column("households", "new_house_id")
