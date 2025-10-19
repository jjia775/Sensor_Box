from __future__ import annotations

import os
from collections.abc import Sequence
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from ..deps import get_db
from ..models import Household, Sensor, SensorReading


class HealthAdviceRequest(BaseModel):
    house_id: str | None = None


class SensorSnapshot(BaseModel):
    id: str
    name: str
    type: str
    location: str | None
    house_id: str | None
    latest_value: float | None
    latest_ts: str | None


class HealthAdviceResponse(BaseModel):
    advice: str
    sensors: list[SensorSnapshot]


router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)


async def _fetch_sensor_snapshots(
    db: AsyncSession,
    house_id: str | None,
) -> Sequence[tuple[Sensor, Household | None, SensorReading | None]]:
    latest_reading_subq = (
        select(
            SensorReading.sensor_id.label("sensor_id"),
            func.max(SensorReading.ts).label("latest_ts"),
        )
        .group_by(SensorReading.sensor_id)
        .subquery()
    )

    latest_reading_alias = aliased(SensorReading)

    stmt = (
        select(Sensor, Household, latest_reading_alias)
        .outerjoin(Household, Sensor.owner_id == Household.id)
        .outerjoin(
            latest_reading_subq,
            latest_reading_subq.c.sensor_id == Sensor.id,
        )
        .outerjoin(
            latest_reading_alias,
            (latest_reading_alias.sensor_id == Sensor.id)
            & (latest_reading_alias.ts == latest_reading_subq.c.latest_ts),
        )
        .options(joinedload(Sensor.household))
        .order_by(Sensor.name.asc())
    )

    if house_id:
        stmt = stmt.where(Household.house_id == house_id)

    res = await db.execute(stmt)
    return res.all()


def _build_prompt(snapshots: list[SensorSnapshot]) -> str:
    if not snapshots:
        return (
            "You are a health analyst reviewing sensor data, but there are currently no "
            "available readings. Provide general wellness guidance suitable for a household."
        )

    lines: list[str] = [
        "You are a health analyst reviewing environmental and biometric sensor data for a household.",
        "Summarise the overall situation, highlight any potential concerns, and provide actionable recommendations.",
        "Base your response ONLY on the provided sensor information. Avoid making diagnoses.",
        "Format the output with short sections for observations, possible health considerations, and suggestions.",
        "Here are the most recent readings:",
    ]

    for snapshot in snapshots:
        location = snapshot.location or "Unknown location"
        house_label = f"house {snapshot.house_id}" if snapshot.house_id else "unknown house"
        value_part = (
            f"value {snapshot.latest_value}"
            if snapshot.latest_value is not None
            else "no recent value"
        )
        ts_part = (
            f"measured at {snapshot.latest_ts}"
            if snapshot.latest_ts
            else "timestamp unavailable"
        )
        lines.append(
            f"- Sensor '{snapshot.name}' ({snapshot.type}) in {location} for {house_label}: {value_part}, {ts_part}."
        )

    lines.append(
        "Explain what the readings might imply for occupant health and suggest practical steps to maintain or improve wellbeing."
    )

    return "\n".join(lines)


def _extract_text_from_gemini_payload(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise KeyError("Missing candidates in Gemini response")

    texts: list[str] = []
    for candidate in candidates:
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str):
                texts.append(text)

    combined = "\n".join(texts).strip()
    if not combined:
        raise KeyError("Gemini response did not contain text content")
    return combined


def _build_fallback_advice(snapshots: list[SensorSnapshot], reason: str) -> str:
    prefix = (
        "Automated Gemini advice is temporarily unavailable. "
        f"Reason: {reason.strip()}"
    )

    if not snapshots:
        return (
            f"{prefix}\n\n"
            "No recent sensor readings were found, so we can only offer general wellbeing tips. "
            "Ensure sensors are online and reporting, maintain good ventilation, stay hydrated, and follow "
            "regular sleep and activity routines."
        )

    lines = [
        prefix,
        "\nManual summary of your latest sensor snapshots:",
    ]

    for snapshot in snapshots:
        location = snapshot.location or "Unknown location"
        house_label = snapshot.house_id or "Unknown house"
        value = (
            f"latest value {snapshot.latest_value}"
            if snapshot.latest_value is not None
            else "no recent value"
        )
        timestamp = snapshot.latest_ts or "timestamp unavailable"
        lines.append(
            f"- {snapshot.name} ({snapshot.type}) in {location} for {house_label}: {value} at {timestamp}."
        )

    lines.extend(
        [
            "\nConsider checking for unusual trends, ensuring comfortable temperature and humidity levels, "
            "and consulting a healthcare professional for personal medical concerns.",
        ]
    )

    return "\n".join(lines)


@router.post("/health-advice", response_model=HealthAdviceResponse)
async def generate_health_advice(
    payload: HealthAdviceRequest,
    db: AsyncSession = Depends(get_db),
):
    rows = await _fetch_sensor_snapshots(db, payload.house_id)

    snapshots: list[SensorSnapshot] = []
    for sensor, household, reading in rows:
        snapshots.append(
            SensorSnapshot(
                id=str(sensor.id),
                name=sensor.name,
                type=sensor.type,
                location=sensor.location,
                house_id=household.house_id if household else None,
                latest_value=reading.value if reading else None,
                latest_ts=reading.ts.isoformat() if getattr(reading, "ts", None) else None,
            )
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        reason = "Gemini API key is not configured"
        logger.warning("%s", reason)
        advice_text = _build_fallback_advice(snapshots, reason)
        return HealthAdviceResponse(advice=advice_text, sensors=snapshots)

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent"

    prompt = _build_prompt(snapshots)

    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                ],
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, params={"key": api_key}, json=request_body)
        response.raise_for_status()
    except httpx.RequestError as exc:
        reason = f"unable to contact Gemini ({exc})"
        logger.exception("Gemini request failed: %s", exc)
        advice_text = _build_fallback_advice(snapshots, reason)
        return HealthAdviceResponse(advice=advice_text, sensors=snapshots)
    except httpx.HTTPStatusError as exc:
        try:
            error_payload = exc.response.json()
        except ValueError:  # pragma: no cover - best effort logging
            error_payload = exc.response.text
        reason = f"Gemini returned HTTP {exc.response.status_code}: {error_payload}".strip()
        logger.warning("Gemini API responded with an error: %s", reason)
        advice_text = _build_fallback_advice(snapshots, reason)
        return HealthAdviceResponse(advice=advice_text, sensors=snapshots)

    try:
        data = response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        reason = "Gemini API returned invalid JSON"
        logger.warning("%s", reason)
        advice_text = _build_fallback_advice(snapshots, reason)
        return HealthAdviceResponse(advice=advice_text, sensors=snapshots)

    try:
        advice_text = _extract_text_from_gemini_payload(data)
    except KeyError as exc:
        reason = "Gemini API response did not contain usable text"
        logger.warning("%s", reason)
        advice_text = _build_fallback_advice(snapshots, reason)
        return HealthAdviceResponse(advice=advice_text, sensors=snapshots)

    return HealthAdviceResponse(advice=advice_text, sensors=snapshots)

