from alembic import op
import sqlalchemy as sa

revision = "aa80ce951315"
down_revision = "c5601524cf0b"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sensors" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sensors")}
        if "serial_number" not in cols:
            op.add_column("sensors", sa.Column("serial_number", sa.String(length=255), nullable=True))

        # 如果有回填逻辑（例如更新已有记录），一定要确保相关表存在
        # if "sensor_meta" in insp.get_table_names():
        #     op.execute(
        #         "UPDATE sensors s SET serial_number = m.serial_number "
        #         "FROM sensor_meta m WHERE s.id = m.sensor_id AND s.serial_number IS NULL"
        #     )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "sensors" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("sensors")}
        if "serial_number" in cols:
            op.drop_column("sensors", "serial_number")
