from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db
from ..models import Household
from ..schemas import HouseholdOut


router = APIRouter(prefix="/api/households", tags=["households"])


@router.get("/", response_model=list[HouseholdOut])
async def list_households(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="Filter by householder name"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    stmt = select(Household)
    if q:
        stmt = stmt.where(Household.householder.ilike(f"%{q}%"))

    stmt = stmt.order_by(Household.householder.asc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    return [HouseholdOut.model_validate(row) for row in rows]
