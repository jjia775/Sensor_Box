import os
from contextlib import suppress
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting import get_admin_recipients, send_simple_email
from app.schemas import RegisterIn, RegisterOut
from app.models import Household
from app.utils import build_house_id
from app.db import get_db

router = APIRouter(prefix="/api", tags=["registration"])


class SimulationConfigError(Exception):
    """Base error for simulation config failures."""


class SimulationConfigSerialNotFound(SimulationConfigError):
    """Raised when the serial number cannot be found in the config."""


_MISSING = object()


def _simulation_api_base() -> str:
    base = os.environ.get("SIMULATION_API_BASE", "http://simulation:8001").strip()
    # base = os.environ.get("SIMULATION_API_BASE", "http://localhost:8001").strip()
    return base.rstrip("/") if base else base


def _field_action(value: object) -> dict[str, Any]:
    if value is _MISSING:
        return {"action": "clear"}
    return {"action": "set", "value": value}


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "Simulation service error"

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail:
        return detail
    return "Simulation service error"


def _parse_previous_state(payload: dict[str, Any]) -> dict[str, object]:
    previous = payload.get("previous_state")
    if not isinstance(previous, dict):
        raise SimulationConfigError("Simulation response missing previous state")

    result: dict[str, object] = {}
    for key in ("house_id", "registered"):
        entry = previous.get(key)
        if isinstance(entry, dict) and entry.get("present"):
            result[key] = entry.get("value")
        else:
            result[key] = _MISSING
    return result


async def _update_simulation_registration(
    serial_number: str,
    *,
    new_house_id: object,
    registered: object,
) -> dict[str, object]:
    base = _simulation_api_base()
    if not base:
        raise SimulationConfigError("Simulation service base URL is not configured")

    payload = {
        "serial_number": serial_number,
        "house_id": _field_action(new_house_id),
        "registered": _field_action(registered),
    }

    timeout = httpx.Timeout(5.0, read=5.0)
    try:
        async with httpx.AsyncClient(base_url=base, timeout=timeout) as client:
            response = await client.post("/api/simulation/register", json=payload)
    except httpx.RequestError as exc:  # pragma: no cover - network failure
        raise SimulationConfigError("Failed to contact simulation service") from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise SimulationConfigSerialNotFound("Serial number not found in simulation config")
    if response.status_code >= 400:
        raise SimulationConfigError(_extract_error_detail(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise SimulationConfigError("Simulation service returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise SimulationConfigError("Simulation service response was not a JSON object")

    return _parse_previous_state(data)


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    first_name = data.first_name.strip()
    last_name = data.last_name.strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="first_name and last_name must not be empty")
    house_id = build_house_id(data.zone, first_name, last_name, data.serial_number)
    householder = " ".join(part for part in (first_name, last_name) if part)
    q1 = select(Household).where(Household.serial_number == data.serial_number)
    q2 = select(Household).where(Household.house_id == house_id)
    if (await db.execute(q1)).scalars().first():
        raise HTTPException(status_code=409, detail="Serial number already exists")
    if (await db.execute(q2)).scalars().first():
        raise HTTPException(status_code=409, detail="House ID conflict")
    try:
        previous_state = await _update_simulation_registration(
            data.serial_number,
            new_house_id=house_id,
            registered=True,
        )
    except SimulationConfigSerialNotFound:
        raise HTTPException(status_code=422, detail="Serial number is not recognized")
    except SimulationConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    obj = Household(
        serial_number=data.serial_number,
        householder=householder,
        phone=data.phone,
        email=data.email,
        address=data.address,
        zone=data.zone,
        house_id=house_id,
    )
    db.add(obj)
    print("INSERT", house_id)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        with suppress(Exception):
            await _update_simulation_registration(
                data.serial_number,
                new_house_id=previous_state.get("house_id", _MISSING),
                registered=previous_state.get("registered", _MISSING),
            )
        raise

    await send_simple_email(
        subject=f"New household registration: {house_id}",
        body="\n".join(
            filter(
                None,
                [
                    "A new household has been registered.",
                    f"House ID: {house_id}",
                    f"Householder: {householder or 'n/a'}",
                    f"Serial number: {data.serial_number}",
                    f"Zone: {data.zone}",
                    f"Phone: {data.phone or 'n/a'}",
                    f"Email: {data.email or 'n/a'}",
                    f"Address: {data.address or 'n/a'}",
                ],
            )
        ),
        to_addrs=get_admin_recipients(),
    )

    return RegisterOut(house_id=house_id)
