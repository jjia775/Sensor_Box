from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import math
from typing import Any, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SensorReading, Sensor
from ..deps import get_db
from ..alerting import THRESHOLDS
from .diseases import DISEASES

router = APIRouter(prefix="/api/charts", tags=["charts"])

logger = logging.getLogger(__name__)

_LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo or timezone.utc


@dataclass(slots=True)
class TimeWindow:
    """Resolved chart window with UTC display bounds and local DB bounds."""

    start: datetime
    end: datetime
    start_bound: datetime
    end_bound: datetime

ALIASES: dict[str, list[str]] = {
    "temp": ["temp", "temperature"],
    "rh": ["rh", "humidity"],
    "pm25": ["pm25", "pm2_5", "pm2.5"],
    "co2": ["co2"],
    "co": ["co"],
    "no2": ["no2"],
    "o2": ["o2"],
    "light_night": ["light_night", "light"],
    "noise_night": ["noise_night", "noise", "noise_dba", "sound_level"],
}

def _parse_interval(s: str) -> timedelta:
    u = s[-1].lower()
    v = int(s[:-1])
    if u == "s": return timedelta(seconds=v)
    if u == "m": return timedelta(minutes=v)
    if u == "h": return timedelta(hours=v)
    if u == "d": return timedelta(days=v)
    raise ValueError("bad interval")

def _bucket(ts: datetime, start: datetime, step: timedelta) -> datetime:
    n = int((ts - start).total_seconds() // step.total_seconds())
    return start + n * step


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_dt(value: Any) -> tuple[datetime, datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("timestamp must be non-empty")

        # datetime.fromisoformat does not understand trailing "Z" so normalise
        # it to an explicit UTC offset. We also accept lowercase variants and
        # values without a "T" separator for backwards compatibility.
        if cleaned[-1] in {"z", "Z"}:
            cleaned = cleaned[:-1] + "+00:00"
        if " " in cleaned and "T" not in cleaned:
            cleaned = cleaned.replace(" ", "T", 1)

        dt = datetime.fromisoformat(cleaned)
    else:
        raise ValueError("timestamp must be datetime or ISO string")

    if dt.tzinfo is None:
        bound = dt.replace(tzinfo=_LOCAL_TIMEZONE)
    else:
        bound = dt.astimezone(_LOCAL_TIMEZONE)

    display = _normalize_dt(bound)
    return display, bound


def _resolve_window(payload: dict) -> TimeWindow:
    start_raw = payload.get("start_ts")
    end_raw = payload.get("end_ts")
    range_raw = payload.get("duration") or payload.get("range")

    if start_raw and end_raw:
        start_display, start_bound = _parse_dt(start_raw)
        end_display, end_bound = _parse_dt(end_raw)
    elif end_raw and range_raw:
        end_display, end_bound = _parse_dt(end_raw)
        delta = _parse_interval(str(range_raw))
        start_display = end_display - delta
        start_bound = end_bound - delta
    elif start_raw and range_raw:
        start_display, start_bound = _parse_dt(start_raw)
        delta = _parse_interval(str(range_raw))
        end_display = start_display + delta
        end_bound = start_bound + delta
    else:
        # fallback to current time window if only one timestamp supplied
        now = datetime.now(timezone.utc)
        if end_raw:
            end_display, end_bound = _parse_dt(end_raw)
        else:
            end_display = _normalize_dt(now)
            end_bound = now.astimezone(_LOCAL_TIMEZONE)
        delta = _parse_interval(str(range_raw or "24h"))
        start_display = end_display - delta
        start_bound = end_bound - delta

    if start_display >= end_display:
        raise ValueError("start_ts must be before end_ts")
    return TimeWindow(start_display, end_display, start_bound, end_bound)


def _compute_risk(metric: str, value: float) -> float:
    cfg = THRESHOLDS.get(metric)
    if not cfg:
        return 0.0
    risk = 0.0
    for line in cfg["lines"]:
        threshold = float(line["value"])
        if line["kind"] == "upper":
            if value <= threshold:
                continue
            diff = value - threshold
            scale = threshold if threshold else 1.0
            risk = max(risk, min(1.0, diff / abs(scale)))
        else:  # lower bound
            if value >= threshold:
                continue
            diff = threshold - value
            scale = threshold if threshold else 1.0
            risk = max(risk, min(1.0, diff / abs(scale)))
    return risk


def _aggregate(values: list[float], agg: str) -> float:
    if not values:
        return float("nan")
    if agg == "min":
        return min(values)
    if agg == "max":
        return max(values)
    if agg == "last":
        return values[-1]
    if agg == "sum":
        return sum(values)
    return sum(values) / len(values)


async def _load_metric_series(
    db: AsyncSession,
    *,
    serial: str | None,
    sensor_ids: Sequence[UUID],
    metric: str,
    start_ts: datetime,
    end_ts: datetime,
    start_bound: datetime,
    end_bound: datetime,
    interval: timedelta,
    agg: str,
):
    types = [t.lower() for t in ALIASES.get(metric, [metric])]

    stmt = select(SensorReading.ts, SensorReading.value).join(
        Sensor, Sensor.id == SensorReading.sensor_id
    )
    stmt = stmt.where(
        func.lower(Sensor.type).in_(types),
        SensorReading.ts >= start_bound,
        SensorReading.ts <= end_bound,
    )

    serial_clause = _build_serial_join_clause(serial) if serial else None
    if sensor_ids:
        stmt = stmt.where(Sensor.id.in_(sensor_ids))
        if serial_clause is not None:
            stmt = stmt.where(or_(Sensor.id.in_(sensor_ids), serial_clause))
    elif serial_clause is not None:
        stmt = stmt.where(serial_clause)
    else:
        return {}

    stmt = stmt.order_by(SensorReading.ts.asc())

    res = await db.execute(stmt)
    rows = res.all()
    if not rows:
        return {}

    base = _normalize_dt(rows[0][0]).replace(second=0, microsecond=0)
    buckets: dict[datetime, list[float]] = {}
    for ts, val in rows:
        ts_norm = _normalize_dt(ts)
        bucket = _bucket(ts_norm, base, interval)
        buckets.setdefault(bucket, []).append(val)

    out: dict[datetime, float] = {}
    for ts_bucket, values in buckets.items():
        out[ts_bucket] = _aggregate(values, agg)
    return out


def _build_serial_join_clause(serial: str) -> Any:
    serial_lower = serial.lower()
    conditions: list[Any] = [
        func.lower(Sensor.serial_number) == serial_lower,
        func.lower(Sensor.meta.op("->>")("serial_number")) == serial_lower,
        func.lower(Sensor.meta.op("->>")("serial")) == serial_lower,
        func.lower(Sensor.meta.op("->>")("sn")) == serial_lower,
        func.lower(SensorReading.attributes.op("->>")("serial_number")) == serial_lower,
        func.lower(SensorReading.attributes.op("->>")("serial")) == serial_lower,
        func.lower(SensorReading.attributes.op("->>")("sn")) == serial_lower,
    ]

    try:
        as_uuid = UUID(serial)
    except Exception:
        as_uuid = None
    if as_uuid:
        conditions.append(Sensor.id == as_uuid)
        conditions.append(SensorReading.sensor_id == as_uuid)
        attr = SensorReading.attributes.op("->>")("sensor_id")
        conditions.append(func.lower(attr) == str(as_uuid))

    return or_(*conditions)


def _build_sensor_only_serial_clause(serial: str) -> Any:
    serial_lower = serial.lower()
    conditions: list[Any] = [
        func.lower(Sensor.serial_number) == serial_lower,
        func.lower(Sensor.meta.op("->>")("serial_number")) == serial_lower,
        func.lower(Sensor.meta.op("->>")("serial")) == serial_lower,
        func.lower(Sensor.meta.op("->>")("sn")) == serial_lower,
    ]

    try:
        as_uuid = UUID(serial)
    except Exception:
        as_uuid = None
    if as_uuid:
        conditions.append(Sensor.id == as_uuid)

    return or_(*conditions)


def _extract_sensor_ref(payload: dict) -> tuple[str | None, UUID | None]:
    serial_raw = (
        payload.get("serial_number")
        or payload.get("serial")
        or payload.get("sensor_serial")
        or payload.get("serial_id")
        or payload.get("sensor_box_id")
    )
    serial = str(serial_raw).strip() if serial_raw else None
    if serial == "":
        serial = None

    sensor_id_raw = (
        payload.get("sensor_id")
        or payload.get("sensor_uuid")
        or payload.get("sensorId")
    )

    sensor_uuid: UUID | None = None
    if sensor_id_raw:
        try:
            sensor_uuid = UUID(str(sensor_id_raw))
        except Exception:
            logger.warning("Invalid sensor_id provided: %s", sensor_id_raw)

    return serial, sensor_uuid


async def _resolve_sensor_ids(
    db: AsyncSession, serial: str | None, sensor_uuid: UUID | None
) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()

    def _add(candidate: UUID | None) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ids.append(candidate)

    if sensor_uuid:
        _add(sensor_uuid)

    serial_clean = serial.strip() if serial else ""
    if serial_clean:
        try:
            _add(UUID(serial_clean))
        except Exception:
            pass

        serial_lower = serial_clean.lower()
        stmt = select(Sensor.id).where(
            or_(
                func.lower(Sensor.serial_number) == serial_lower,
                func.lower(Sensor.meta.op("->>")("serial_number")) == serial_lower,
                func.lower(Sensor.meta.op("->>")("serial")) == serial_lower,
                func.lower(Sensor.meta.op("->>")("sn")) == serial_lower,
            )
        )
        res = await db.execute(stmt)
        for (sensor_id,) in res.all():
            _add(sensor_id)

    return ids


def _log_request(prefix: str, **kwargs: Any) -> None:
    safe = {k: v for k, v in kwargs.items()}
    for key in ("series", "points", "rows"):
        safe.pop(key, None)
    logger.info("[charts] %s: %s", prefix, safe)

@router.get("/metrics")
def list_metrics():
    out = []
    for k, cfg in THRESHOLDS.items():
        out.append({"metric": k, "unit": cfg["unit"], "thresholds": cfg["lines"]})
    return {"metrics": out}

@router.post("/metric_timeseries")
async def metric_timeseries(payload: dict, db: AsyncSession = Depends(get_db)):
    serial, sensor_uuid = _extract_sensor_ref(payload)
    if not serial and not sensor_uuid:
        return {
            "title": "Missing serial reference",
            "unit": "",
            "labels": [],
            "series": [{"name": "n/a", "data": []}],
            "thresholds": [],
        }

    metric = str(payload["metric"]).lower()
    cfg = THRESHOLDS.get(metric, {"unit": "", "lines": []})

    try:
        window = _resolve_window(payload)
    except Exception:
        return {
            "title": "Invalid time range",
            "unit": cfg.get("unit", ""),
            "labels": [],
            "series": [{"name": metric, "data": []}],
            "thresholds": cfg.get("lines", []),
        }
    interval = _parse_interval(payload.get("interval", "5m"))
    agg = payload.get("agg", "avg")
    title = payload.get("title") or f"{metric.upper()} vs Time"

    sensor_ids = await _resolve_sensor_ids(db, serial, sensor_uuid)
    _log_request(
        "metric_timeseries_request",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        metric=metric,
        start=window.start.isoformat(),
        end=window.end.isoformat(),
        interval=str(interval),
        agg=agg,
    )

    series_map = await _load_metric_series(
        db,
        serial=serial,
        sensor_ids=sensor_ids,
        metric=metric,
        start_ts=window.start,
        end_ts=window.end,
        start_bound=window.start_bound,
        end_bound=window.end_bound,
        interval=interval,
        agg=agg,
    )

    if not series_map:
        _log_request(
            "metric_timeseries_empty",
            serial=serial,
            sensor_ids=[str(s) for s in sensor_ids],
            metric=metric,
            buckets=0,
        )
        return {
            "title": title,
            "unit": cfg["unit"],
            "labels": [],
            "series": [{"name": metric, "data": []}],
            "thresholds": cfg["lines"],
        }

    labels, data = [], []
    for k in sorted(series_map.keys()):
        labels.append(k.isoformat())
        data.append(series_map[k])

    _log_request(
        "metric_timeseries_response",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        metric=metric,
        points=len(data),
    )

    return {"title": title, "unit": cfg["unit"], "labels": labels, "series": [{"name": metric, "data": data}], "thresholds": cfg["lines"]}


@router.post("/metric_scatter")
async def metric_scatter(payload: dict, db: AsyncSession = Depends(get_db)):
    serial, sensor_uuid = _extract_sensor_ref(payload)
    if not serial and not sensor_uuid:
        return {
            "title": "Missing serial reference",
            "unit_x": "",
            "unit_y": "",
            "points": [],
            "best_fit": None,
            "x_thresholds": [],
            "y_thresholds": [],
        }

    x_metric = str(payload.get("x_metric", "")).lower()
    y_metric = str(payload.get("y_metric", "")).lower()
    if not x_metric or not y_metric:
        return {
            "title": "Missing metrics",
            "unit_x": "",
            "unit_y": "",
            "points": [],
            "best_fit": None,
            "x_thresholds": [],
            "y_thresholds": [],
        }

    try:
        window = _resolve_window(payload)
    except Exception:
        return {
            "title": "Invalid time range",
            "unit_x": THRESHOLDS.get(x_metric, {}).get("unit", ""),
            "unit_y": THRESHOLDS.get(y_metric, {}).get("unit", ""),
            "points": [],
            "best_fit": None,
            "x_thresholds": THRESHOLDS.get(x_metric, {}).get("lines", []),
            "y_thresholds": THRESHOLDS.get(y_metric, {}).get("lines", []),
        }

    interval = _parse_interval(payload.get("interval", "5m"))
    agg = payload.get("agg", "avg")
    title = payload.get("title") or f"{x_metric.upper()} vs {y_metric.upper()}"

    sensor_ids = await _resolve_sensor_ids(db, serial, sensor_uuid)
    _log_request(
        "metric_scatter_request",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        x_metric=x_metric,
        y_metric=y_metric,
        start=window.start.isoformat(),
        end=window.end.isoformat(),
        interval=str(interval),
        agg=agg,
    )

    x_map = await _load_metric_series(
        db,
        serial=serial,
        sensor_ids=sensor_ids,
        metric=x_metric,
        start_ts=window.start,
        end_ts=window.end,
        start_bound=window.start_bound,
        end_bound=window.end_bound,
        interval=interval,
        agg=agg,
    )
    y_map = await _load_metric_series(
        db,
        serial=serial,
        sensor_ids=sensor_ids,
        metric=y_metric,
        start_ts=window.start,
        end_ts=window.end,
        start_bound=window.start_bound,
        end_bound=window.end_bound,
        interval=interval,
        agg=agg,
    )

    points = []
    for bucket in sorted(set(x_map.keys()) & set(y_map.keys())):
        xv = x_map[bucket]
        yv = y_map[bucket]
        if xv is None or yv is None:
            continue
        if isinstance(xv, float) and math.isnan(xv):
            continue
        if isinstance(yv, float) and math.isnan(yv):
            continue
        points.append({"ts": bucket.isoformat(), "x": float(xv), "y": float(yv)})

    best_fit = None
    if len(points) >= 2:
        n = len(points)
        sum_x = sum(p["x"] for p in points)
        sum_y = sum(p["y"] for p in points)
        sum_xy = sum(p["x"] * p["y"] for p in points)
        sum_x2 = sum(p["x"] * p["x"] for p in points)
        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) > 1e-12:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n
            best_fit = {"slope": slope, "intercept": intercept}

    _log_request(
        "metric_scatter_response",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        x_metric=x_metric,
        y_metric=y_metric,
        points=len(points),
        best_fit=bool(best_fit),
    )

    return {
        "title": title,
        "unit_x": THRESHOLDS.get(x_metric, {}).get("unit", ""),
        "unit_y": THRESHOLDS.get(y_metric, {}).get("unit", ""),
        "points": points,
        "best_fit": best_fit,
        "x_thresholds": THRESHOLDS.get(x_metric, {}).get("lines", []),
        "y_thresholds": THRESHOLDS.get(y_metric, {}).get("lines", []),
    }


@router.post("/risk_heatmap")
async def risk_heatmap(payload: dict, db: AsyncSession = Depends(get_db)):
    serial, sensor_uuid = _extract_sensor_ref(payload)
    if not serial and not sensor_uuid:
        return {
            "title": "Missing serial reference",
            "start": None,
            "end": None,
            "interval": payload.get("interval", "1h"),
            "labels": [],
            "rows": [],
        }

    try:
        window = _resolve_window(payload)
    except Exception:
        return {
            "title": payload.get("title") or "Risk Heatmap",
            "start": None,
            "end": None,
            "interval": payload.get("interval", "1h"),
            "labels": [],
            "rows": [],
        }

    interval = _parse_interval(payload.get("interval", "1h"))
    agg = payload.get("agg", "avg")
    disease_key = payload.get("disease_key") or payload.get("disease")
    disease_metrics: list[str] | None = None
    if disease_key:
        for d in DISEASES:
            if d.get("key") == disease_key:
                disease_metrics = [str(m).lower() for m in d.get("metrics", []) if str(m).strip()]
                break

    metrics = payload.get("metrics") or disease_metrics or list(THRESHOLDS.keys())
    metrics = [str(m).lower() for m in metrics if str(m).strip()]
    metrics = [m for m in metrics if m in THRESHOLDS]
    if not metrics:
        return {
            "title": payload.get("title") or "Risk Heatmap",
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "interval": payload.get("interval", "1h"),
            "labels": [],
            "rows": [],
        }

    sensor_ids = await _resolve_sensor_ids(db, serial, sensor_uuid)
    _log_request(
        "risk_heatmap_request",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        metrics=metrics,
        disease=disease_key,
        start=window.start.isoformat(),
        end=window.end.isoformat(),
        interval=str(interval),
        agg=agg,
    )

    alias_to_metric: dict[str, str] = {}
    for metric in metrics:
        for alias in ALIASES.get(metric, [metric]):
            alias_to_metric[alias.lower()] = metric

    sensor_stmt = select(func.lower(Sensor.type), Sensor.meta).where(
        func.lower(Sensor.type).in_(alias_to_metric.keys())
    )

    if sensor_ids:
        sensor_stmt = sensor_stmt.where(Sensor.id.in_(sensor_ids))
    elif serial:
        sensor_stmt = sensor_stmt.where(_build_sensor_only_serial_clause(serial))
    else:
        return {
            "title": payload.get("title") or "Risk Heatmap",
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "interval": payload.get("interval", "1h"),
            "labels": [],
            "rows": [],
        }

    sensor_rows = (await db.execute(sensor_stmt)).all()

    metric_has_sensor: dict[str, bool] = {m: False for m in metrics}
    metric_enabled: dict[str, bool] = {m: False for m in metrics}
    metric_disabled_explicit: set[str] = set()
    for sensor_type, meta in sensor_rows:
        metric = alias_to_metric.get(sensor_type)
        if not metric:
            continue
        metric_has_sensor[metric] = True
        enabled = True
        if isinstance(meta, dict) and "enabled" in meta:
            enabled = bool(meta["enabled"])
            if not enabled:
                metric_disabled_explicit.add(metric)
        if enabled:
            metric_enabled[metric] = True

    stmt = select(func.lower(Sensor.type), SensorReading.ts, SensorReading.value).join(
        Sensor, Sensor.id == SensorReading.sensor_id
    )
    stmt = stmt.where(
        func.lower(Sensor.type).in_(alias_to_metric.keys()),
        SensorReading.ts >= window.start_bound,
        SensorReading.ts <= window.end_bound,
    )

    serial_clause = _build_serial_join_clause(serial) if serial else None
    if sensor_ids:
        stmt = stmt.where(Sensor.id.in_(sensor_ids))
        if serial_clause is not None:
            stmt = stmt.where(or_(Sensor.id.in_(sensor_ids), serial_clause))
    elif serial_clause is not None:
        stmt = stmt.where(serial_clause)
    else:
        return {
            "title": payload.get("title") or "Risk Heatmap",
            "start": window.start.isoformat(),
            "end": window.end.isoformat(),
            "interval": payload.get("interval", "1h"),
            "labels": [],
            "rows": [],
        }

    stmt = stmt.order_by(SensorReading.ts.asc())
    res = await db.execute(stmt)
    rows = res.all()

    duration = window.end - window.start
    steps = max(1, math.ceil(duration.total_seconds() / interval.total_seconds()))
    labels_dt = [window.start + i * interval for i in range(steps)]
    step_seconds = interval.total_seconds()

    metric_buckets: dict[str, dict[int, list[float]]] = {m: {} for m in metrics}

    for sensor_type, ts, value in rows:
        metric = alias_to_metric.get(sensor_type)
        if metric is None:
            continue
        metric_has_sensor[metric] = True
        if metric not in metric_disabled_explicit and not metric_enabled.get(metric):
            metric_enabled[metric] = True
        ts_norm = _normalize_dt(ts)
        delta = (ts_norm - window.start).total_seconds()
        if delta < 0:
            continue
        idx = int(delta // step_seconds)
        if idx >= steps:
            idx = steps - 1
        metric_buckets.setdefault(metric, {}).setdefault(idx, []).append(value)

    heatmap_rows = []
    for metric in metrics:
        cfg = THRESHOLDS.get(metric, {"unit": "", "lines": []})
        buckets = metric_buckets.get(metric, {})
        values: list[float | None] = []
        risks: list[float | None] = []
        for i in range(steps):
            vals = buckets.get(i)
            if not vals:
                values.append(None)
                risks.append(None)
                continue
            if agg == "min":
                v = min(vals)
            elif agg == "max":
                v = max(vals)
            elif agg == "last":
                v = vals[-1]
            elif agg == "sum":
                v = sum(vals)
            else:
                v = sum(vals) / len(vals)
            values.append(v)
            risks.append(_compute_risk(metric, v))
        heatmap_rows.append({
            "metric": metric,
            "unit": cfg.get("unit", ""),
            "thresholds": cfg.get("lines", []),
            "values": values,
            "risk": risks,
            "enabled": metric_enabled.get(metric, False),
            "has_sensor": metric_has_sensor.get(metric, False),
        })

    _log_request(
        "risk_heatmap_response",
        serial=serial,
        sensor_ids=[str(s) for s in sensor_ids],
        metrics=metrics,
        rows=len(heatmap_rows),
        labels=len(labels_dt),
    )

    return {
        "title": payload.get("title") or "Risk Heatmap",
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "interval": payload.get("interval", "1h"),
        "labels": [dt.isoformat() for dt in labels_dt],
        "rows": heatmap_rows,
    }
