# app/routers/diseases.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/diseases", tags=["diseases"])

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "diseases.json"

# Adjust these as needed: key, display name, and associated metric keys
# Metric keys must match the ones returned by /api/charts/metrics (e.g. temp, co2, pm25, rh, no2, co, o2, light_night, noise_night)
DEFAULT_DISEASES: list[dict[str, Any]] = [
    {
        "key": "disease1",
        "name": "D1",
        "metrics": ["temp", "co2"],  # e.g. disease1 uses temperature and CO2
    },
    {
        "key": "asthma",
        "name": "D2",
        "metrics": ["pm25", "no2", "co2", "rh"],
    },
    {
        "key": "sleep",
        "name": "Sleep disorder",
        "metrics": ["noise_night", "light_night", "temp", "rh"],
    },
]


class DiseasePayload(BaseModel):
    key: str = Field(..., description="Unique disease key")
    name: str = Field(..., description="Display name of the disease")
    metrics: list[str] = Field(default_factory=list, description="List of associated metric keys")


class DiseaseUpdatePayload(BaseModel):
    name: str | None = Field(default=None, description="Updated disease name")
    metrics: list[str] | None = Field(default=None, description="Updated list of metric keys")


def _normalize_metrics(metrics: list[str] | None) -> list[str]:
    """Normalize metrics: drop empty values, lower-case them, and keep order uniqueness."""

    if not metrics:
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for raw in metrics:
        metric = str(raw).strip().lower()
        if not metric or metric in seen:
            continue
        seen.add(metric)
        normalized.append(metric)
    return normalized


def _ensure_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Disease key is required")
    return key



def _normalise_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Coerce an arbitrary dictionary into a disease definition if possible."""

    key = str(entry.get("key") or "").strip()
    if not key:
        return None

    name = str(entry.get("name") or "").strip() or key
    metrics = entry.get("metrics") if isinstance(entry.get("metrics"), list) else []
    return {"key": key, "name": name, "metrics": _normalize_metrics(metrics)}


def _default_diseases() -> list[dict[str, Any]]:
    return [
        {
            "key": disease["key"],
            "name": disease["name"],
            "metrics": _normalize_metrics(disease.get("metrics")),
        }
        for disease in DEFAULT_DISEASES
    ]


def _write_diseases(diseases: list[dict[str, Any]]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(diseases, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_diseases() -> list[dict[str, Any]]:
    try:
        if not DATA_FILE.exists():
            diseases = _default_diseases()
            _write_diseases(diseases)
            return diseases

        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        diseases: list[dict[str, Any]] = []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    normalised = _normalise_entry(item)
                    if normalised:
                        diseases.append(normalised)

        if not diseases:
            diseases = _default_diseases()

        _write_diseases(diseases)
        return diseases
    except OSError:
        # I/O errors should not break the application start-up; fall back to defaults.
        return _default_diseases()
    except json.JSONDecodeError:
        diseases = _default_diseases()
        try:
            _write_diseases(diseases)
        except OSError:
            pass
        return diseases


def _save_diseases() -> None:
    try:
        _write_diseases(DISEASES)
    except OSError as exc:  # pragma: no cover - surfaced via HTTPException below
        raise HTTPException(status_code=500, detail="Failed to persist disease configuration") from exc


DISEASES = _load_diseases()


@router.get("/", summary="List all diseases and their associated metrics")
def list_diseases():
    return {"diseases": DISEASES}

@router.get("/{key}", summary="Get a single disease definition")
def get_disease(key: str):
    for d in DISEASES:
        if d["key"] == key:
            return d
    raise HTTPException(status_code=404, detail="Disease not found")


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a disease configuration")
def create_disease(payload: DiseasePayload):
    key = _ensure_key(payload.key)
    for disease in DISEASES:
        if disease["key"] == key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Disease key already exists")

    name = str(payload.name or "").strip() or key
    metrics = _normalize_metrics(payload.metrics)
    disease = {"key": key, "name": name, "metrics": metrics}
    DISEASES.append(disease)
    _save_diseases()
    return disease


@router.put("/{key}", summary="Update a disease configuration")
def update_disease(key: str, payload: DiseaseUpdatePayload):
    for disease in DISEASES:
        if disease["key"] == key:
            if payload.name is not None:
                name = str(payload.name or "").strip()
                if name:
                    disease["name"] = name
            if payload.metrics is not None:
                disease["metrics"] = _normalize_metrics(payload.metrics)
            _save_diseases()
            return disease
    raise HTTPException(status_code=404, detail="Disease not found")


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a disease configuration")
def delete_disease(key: str):
    for idx, disease in enumerate(DISEASES):
        if disease["key"] == key:
            DISEASES.pop(idx)
            _save_diseases()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=404, detail="Disease not found")
