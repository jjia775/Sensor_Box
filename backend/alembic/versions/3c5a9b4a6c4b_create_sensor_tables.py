"""create sensor related tables"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3c5a9b4a6c4b"
down_revision: Union[str, Sequence[str], None] = "aa80ce951315"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("type", sa.String(length=80), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("serial_number", sa.String(length=64), nullable=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("households.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB, nullable=True),
    )
    op.create_index(op.f("ix_sensors_name"), "sensors", ["name"], unique=False)
    op.create_index(op.f("ix_sensors_type"), "sensors", ["type"], unique=False)
    op.create_index(
        op.f("ix_sensors_serial_number"), "sensors", ["serial_number"], unique=False
    )
    op.create_index(op.f("ix_sensors_owner_id"), "sensors", ["owner_id"], unique=False)

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "sensor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("attributes", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        op.f("ix_sensor_readings_sensor_id"),
        "sensor_readings",
        ["sensor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sensor_readings_ts"), "sensor_readings", ["ts"], unique=False
    )
    op.create_index(
        "ix_readings_sensor_ts_desc",
        "sensor_readings",
        ["sensor_id", "ts"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"ts": "DESC"},
    )

    op.create_table(
        "sensor_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "sensor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_sensor_configs_sensor_id"), "sensor_configs", ["sensor_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sensor_configs_sensor_id"), table_name="sensor_configs")
    op.drop_table("sensor_configs")

    op.drop_index("ix_readings_sensor_ts_desc", table_name="sensor_readings")
    op.drop_index(op.f("ix_sensor_readings_ts"), table_name="sensor_readings")
    op.drop_index(op.f("ix_sensor_readings_sensor_id"), table_name="sensor_readings")
    op.drop_table("sensor_readings")

    op.drop_index(op.f("ix_sensors_owner_id"), table_name="sensors")
    op.drop_index(op.f("ix_sensors_serial_number"), table_name="sensors")
    op.drop_index(op.f("ix_sensors_type"), table_name="sensors")
    op.drop_index(op.f("ix_sensors_name"), table_name="sensors")
    op.drop_table("sensors")
