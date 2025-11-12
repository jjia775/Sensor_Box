from uuid import UUID
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from ..deps import get_db
from ..models import Sensor, Household
from ..schemas import SensorCreate, SensorOut
from datetime import datetime
import httpx

try:
    from app.simulation.home_env_sim import HomeEnvSim  # noqa
    from app.simulation.lorawan_encode import encode_lorawan, to_hex  # noqa
    HAVE_SIM = True
except Exception:
    HAVE_SIM = False

router = APIRouter(prefix="/sensors", tags=["sensors"])


def to_sensor_out(row: Sensor) -> SensorOut:
    household = getattr(row, "household", None)
    house_id = getattr(household, "house_id", None) if household else None
    householder = getattr(household, "householder", None) if household else None
    return SensorOut(
        id=row.id,
        name=row.name,
        type=row.type,
        location=row.location,
        serial_number=row.serial_number,   # newly added field
        meta=row.meta or {},
        house_id=house_id,
        householder=householder,
    )



@router.get("/", response_model=list[SensorOut])
async def list_sensors(
    db: AsyncSession = Depends(get_db),
    sensor_type: str | None = None,
    q: str | None = None,
    house_id: str | None = Query(None),
    owner_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    stmt = select(Sensor).options(selectinload(Sensor.household))
    if sensor_type:
        stmt = stmt.where(Sensor.type == sensor_type)
    if q:
        stmt = stmt.where(Sensor.name.ilike(f"%{q}%"))

    if owner_id is not None:
        stmt = stmt.where(Sensor.owner_id == owner_id)
    elif house_id:
        sub = select(Household.id).where(Household.house_id == house_id).scalar_subquery()
        stmt = stmt.where(Sensor.owner_id == sub)
        # If you still need to support legacy data where owner_id is empty but meta contains house_id, add:
        # from sqlalchemy import or_, cast, String
        # stmt = stmt.where(or_(Sensor.owner_id == sub, cast(Sensor.meta['house_id'], String) == house_id))

    stmt = stmt.order_by(Sensor.name.asc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [to_sensor_out(r) for r in rows]



@router.get("/{sensor_id}", response_model=SensorOut)
async def get_sensor(sensor_id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Sensor).options(selectinload(Sensor.household)).where(Sensor.id == sensor_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")
    return to_sensor_out(obj)


@router.post("/", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
async def create_sensor(
    payload: SensorCreate,
    db: AsyncSession = Depends(get_db),
    owner_id: int | None = Query(None),
    house_id: str | None = Query(None),
    householder: str | None = Query(None),
):
    from ..models import Household
    stmt = None
    if owner_id is not None:
        stmt = select(Household).where(Household.id == owner_id)
    elif house_id:
        stmt = select(Household).where(Household.house_id == house_id)
    elif householder:
        stmt = select(Household).where(Household.householder == householder)
    else:
        raise HTTPException(status_code=400, detail="one of house_id / owner_id / householder is required")

    res = await db.execute(stmt)
    hh = res.scalars().first()
    if not hh:
        raise HTTPException(status_code=404, detail="Household not found")

    data = payload.model_dump()
    serial = data.get("serial_number")
    obj = Sensor(
        name=data.get("name"),
        type=data.get("type") or data.get("sensor_type"),
        location=data.get("location"),
        serial_number=serial,
        meta=data.get("meta") or data.get("metadata") or {},
        owner_id=hh.id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj, attribute_names=["household"])
    return to_sensor_out(obj)




@router.patch("/{sensor_id}", response_model=SensorOut)
async def update_sensor(sensor_id: UUID, payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Sensor).options(selectinload(Sensor.household)).where(Sensor.id == sensor_id)
    )
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")

    if "name" in payload and payload["name"] is not None:
        obj.name = payload["name"]

    if "type" in payload and payload["type"] is not None:
        obj.type = payload["type"]
    elif "sensor_type" in payload and payload["sensor_type"] is not None:
        obj.type = payload["sensor_type"]

    if "location" in payload and payload["location"] is not None:
        obj.location = payload["location"]

    if "metadata" in payload and payload["metadata"] is not None:
        obj.meta = payload["metadata"]
    elif "meta" in payload and payload["meta"] is not None:
        obj.meta = payload["meta"]

    # Support remotely toggling the "enabled" flag
    if "enabled" in payload:
        # Reassign the metadata dictionary instead of mutating it in-place so that
        # SQLAlchemy reliably detects changes to JSONB fields. Without this,
        # toggling the enabled flag might appear to succeed on the frontend while
        # the database state (and therefore the ingest behaviour) remains
        # unchanged.
        current_meta = obj.meta or {}
        obj.meta = {**current_meta, "enabled": bool(payload["enabled"])}

    await db.commit()
    await db.refresh(obj, attribute_names=["household"])
    return to_sensor_out(obj)


@router.delete("/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(sensor_id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Sensor).where(Sensor.id == sensor_id))
    obj = res.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")
    await db.delete(obj)
    await db.commit()
    return


@router.post("/{sensor_id}/simulate")
async def simulate_sensor(
    sensor_id: UUID,
    hours: int = Query(1, ge=1, le=24),
    period_minutes: int = Query(5, ge=1, le=60),
    profile: str = Query("intermittent"),
    seed: int = 123,
    ingest_url: str = Query("http://localhost:8000/ingest"),
    db: AsyncSession = Depends(get_db),
):
    if not HAVE_SIM:
        raise HTTPException(status_code=503, detail="Simulation modules not available")

    res = await db.execute(select(Sensor).where(Sensor.id == sensor_id))
    sensor = res.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")

    start = datetime.now().replace(second=0, microsecond=0)
    sim = HomeEnvSim(profile=profile, period_minutes=period_minutes, seed=seed)
    window = sim.generate_window(start, hours=hours)

    sent = 0
    async with httpx.AsyncClient(timeout=5) as client:
        for dt, esp in window:
            value = None
            attributes = {"ts": dt.isoformat()}

            if isinstance(esp, (int, float)):
                value = float(esp)
            elif isinstance(esp, dict):
                for k in ("value", "temperature", "temp", "humidity", "pm2_5", "co2"):
                    if k in esp and isinstance(esp[k], (int, float)):
                        value = float(esp[k])
                        break
                attributes["raw"] = esp
            else:
                attributes["raw"] = str(esp)

            if value is None:
                continue

            payload = {"sensor_id": str(sensor.id), "value": value, "attributes": attributes}
            try:
                r = await client.post(ingest_url, json=payload)
                if r.status_code >= 300:
                    print(f"[WARN] ingest failed {r.status_code}: {r.text}")
                else:
                    sent += 1
            except httpx.RequestError as e:
                print(f"[ERROR] HTTP error posting ingest: {e}")

    return {"ok": True, "sent": sent}
