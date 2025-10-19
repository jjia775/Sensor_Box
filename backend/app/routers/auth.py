# app/auth.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Household  # Important: existing model
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


# Request/response models (keep them simple)
class LoginRequest(BaseModel):
    house_id: str


class LoginResponse(BaseModel):
    ok: bool
    house_id: str


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    hid = (payload.house_id or "").strip()
    if not hid:
        raise HTTPException(status_code=400, detail="house_id is required")

    stmt = select(Household).where(Household.house_id == hid)
    result = await db.execute(stmt)
    household: Optional[Household] = result.scalar_one_or_none()

    if not household:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="House not found")

    # Persist session (cookie)
    request.session["house_id"] = hid
    request.session["role"] = "house"

    return {"ok": True, "house_id": hid}


@router.post("/logout")
async def logout(request: Request, response: Response):
    request.session.clear()
    return {"ok": True}


# Dependency: use this to obtain the current house_id for endpoints that require login
def require_house(request: Request) -> str:
    hid = request.session.get("house_id")
    if not hid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return hid
