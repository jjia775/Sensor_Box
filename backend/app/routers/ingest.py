from datetime import datetime, timezone
from typing import Any, List, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..alerting import (
    ThresholdBreach,
    dispatch_alerts,
    evaluate_thresholds,
    get_metric_unit,
)
from ..deps import get_db
from ..models import Household, Sensor, SensorReading

router = APIRouter(tags=["ingest"])

# Simple input coercion (dict payloads are also accepted)
def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    try:
        sid = UUID(str(row["sensor_id"]))
        val = float(row["value"])
    except Exception:
        raise HTTPException(status_code=400, detail="bad sensor_id or value")
    attrs = row.get("attributes") or {}
    if not isinstance(attrs, dict):
        attrs = {}
    return {"sensor_id": sid, "value": val, "attributes": attrs}

def _is_sensor_enabled(sensor: Sensor) -> bool:
    meta = sensor.meta if isinstance(sensor.meta, dict) else {}
    if "enabled" not in meta:
        return True
    value = meta["enabled"]
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "off", "no"}
    return bool(value)


@router.post("/ingest")
async def ingest(payload: Union[dict, List[dict]], db: AsyncSession = Depends(get_db)):
    rows = payload if isinstance(payload, list) else [payload]
    data = [_coerce_row(r) for r in rows]

    sensor_ids = {row["sensor_id"] for row in data}
    sensors: dict[UUID, Sensor] = {}
    if sensor_ids:
        stmt = select(Sensor).where(Sensor.id.in_(tuple(sensor_ids)))
        sensor_rows = await db.execute(stmt)
        sensors = {sensor.id: sensor for sensor in sensor_rows.scalars()}

    owner_ids = {sensor.owner_id for sensor in sensors.values() if sensor and sensor.owner_id}
    households: dict[int, Household] = {}
    if owner_ids:
        stmt = select(Household).where(Household.id.in_(tuple(owner_ids)))
        household_rows = await db.execute(stmt)
        households = {household.id: household for household in household_rows.scalars()}

    events: list[ThresholdBreach] = []
    filtered: list[dict[str, Any]] = []
    for row in data:
        sensor = sensors.get(row["sensor_id"])
        if not sensor or not sensor.type:
            continue
        if not _is_sensor_enabled(sensor):
            continue

        filtered.append(row)
        metric = sensor.type.lower()
        triggered = evaluate_thresholds(metric, row["value"])
        if not triggered:
            continue
        attrs = row.get("attributes") or {}
        unit = get_metric_unit(metric)
        sensor_serial = sensor.serial_number or attrs.get("serial_number")
        recorded_at = datetime.now(timezone.utc)
        recipients: tuple[str, ...] | None = None
        candidate_recipients: list[str] = []
        if sensor and sensor.owner_id:
            household = households.get(sensor.owner_id)
            if household and household.email:
                email = household.email.strip()
                if email:
                    candidate_recipients.append(email)
        if candidate_recipients:
            recipients = tuple(dict.fromkeys(candidate_recipients))

        for line in triggered:
            try:
                threshold_value = float(line["value"])
            except (KeyError, TypeError, ValueError):
                continue
            events.append(
                ThresholdBreach(
                    metric=metric,
                    value=row["value"],
                    threshold=threshold_value,
                    threshold_kind=str(line.get("kind", "")),
                    label=str(line.get("label", "")),
                    unit=unit,
                    sensor_id=str(row["sensor_id"]),
                    sensor_name=sensor.name,
                    sensor_serial=sensor_serial,
                    recorded_at=recorded_at,
                    recipients=recipients,
                )
            )

    if not filtered:
        return {"ok": True, "n": 0}

    # Writes should only insert. Avoid JOINs, sensor lookups, or other heavy logic here.
    # Optional: disable synchronous commit to reduce persistence latency (risking the newest rows on power loss) and improve throughput
    await db.execute(text("SET LOCAL synchronous_commit = OFF"))

    stmt = insert(SensorReading).values(filtered)
    await db.execute(stmt)
    await db.commit()
    await dispatch_alerts(events)
    return {"ok": True, "n": len(filtered)}
