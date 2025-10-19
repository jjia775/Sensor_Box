from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime
from ..models import SensorReading
from ..deps import get_db
from typing import Iterable
import csv
from io import StringIO
import json


def _parse_iso_datetime(value: str | None, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}. Use ISO-8601 format.") from exc


async def _fetch_readings(
    db: AsyncSession,
    sensor_id: str,
    start_dt: datetime | None,
    end_dt: datetime | None,
    limit: int,
) -> list[SensorReading]:
    stmt = select(SensorReading).where(SensorReading.sensor_id == sensor_id)
    if start_dt:
        stmt = stmt.where(SensorReading.ts >= start_dt)
    if end_dt:
        stmt = stmt.where(SensorReading.ts <= end_dt)
    stmt = stmt.order_by(desc(SensorReading.ts)).limit(limit)

    res = await db.execute(stmt)
    rows = res.scalars().all()
    # Return ascending order to make visualisation easier to read
    return rows[::-1]

router = APIRouter()

@router.post("/api/readings/query")
async def query_readings(payload: dict, db: AsyncSession = Depends(get_db)):
    sensor_id = payload["sensor_id"]
    start_ts = payload.get("start_ts")
    end_ts = payload.get("end_ts")
    limit = int(payload.get("limit", 500))

    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be greater than zero")
    if limit > 10000:
        raise HTTPException(status_code=400, detail="limit must be less than or equal to 10000")

    start_dt = _parse_iso_datetime(start_ts, "start_ts")
    end_dt = _parse_iso_datetime(end_ts, "end_ts")

    rows = await _fetch_readings(db, sensor_id, start_dt, end_dt, limit)

    return [
        {
            "id": r.id,
            "sensor_id": str(r.sensor_id),
            "ts": r.ts.isoformat(),
            "value": r.value,
            "attributes": r.attributes,
        }
        for r in rows
    ]


def _render_csv(rows: Iterable[SensorReading]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "sensor_id", "timestamp", "value", "attributes"])
    for r in rows:
        writer.writerow(
            [
                r.id,
                str(r.sensor_id),
                r.ts.isoformat(),
                r.value,
                "" if r.attributes is None else json.dumps(r.attributes, ensure_ascii=False),
            ]
        )
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/api/readings/export")
async def export_readings(
    sensor_id: str,
    start_ts: str | None = None,
    end_ts: str | None = None,
    limit: int = Query(500, gt=0, le=10000),
    db: AsyncSession = Depends(get_db),
):
    start_dt = _parse_iso_datetime(start_ts, "start_ts")
    end_dt = _parse_iso_datetime(end_ts, "end_ts")

    rows = await _fetch_readings(db, sensor_id, start_dt, end_dt, limit)

    csv_content = _render_csv(rows)
    filename = f"sensor_{sensor_id}_readings.csv"
    response = StreamingResponse(iter([csv_content]), media_type="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
