import uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, Boolean, TIMESTAMP, text, ForeignKey, Float, BigInteger, Index, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

class Base(DeclarativeBase):
    pass

class Household(Base):
    __tablename__ = "households"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    householder: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    zone: Mapped[str] = mapped_column(String(1), nullable=False)
    house_id: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sensors: Mapped[list["Sensor"]] = relationship("Sensor", back_populates="household", cascade="all, delete-orphan", passive_deletes=True)

class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)  # newly added field
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("households.id", ondelete="SET NULL"), index=True, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    household: Mapped["Household"] = relationship("Household", back_populates="sensors")
    readings = relationship("SensorReading", back_populates="sensor", cascade="all, delete-orphan", passive_deletes=True)
    configs = relationship("SensorConfig", back_populates="sensor", cascade="all, delete-orphan", passive_deletes=True)

class SensorReading(Base):
    __tablename__ = "sensor_readings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="CASCADE"), index=True)
    ts: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"), index=True)
    value: Mapped[float] = mapped_column(Float)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sensor = relationship("Sensor", back_populates="readings")

Index("ix_readings_sensor_ts_desc", SensorReading.sensor_id, SensorReading.ts.desc())

class SensorConfig(Base):
    __tablename__ = "sensor_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sensors.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    sensor = relationship("Sensor", back_populates="configs")
