import uuid
from typing import Optional, Any, Literal
from pydantic import BaseModel, EmailStr, Field, AliasChoices, ConfigDict

class SensorCreate(BaseModel):
    name: str
    type: str = Field(validation_alias=AliasChoices("type", "sensor_type"))
    location: Optional[str] = None
    serial_number: Optional[str] = Field(default=None, validation_alias=AliasChoices("serial_number", "serial", "sn"))
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias=AliasChoices("metadata", "meta"))



class SensorUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = Field(default=None, validation_alias=AliasChoices("type", "sensor_type"))
    location: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[dict[str, Any]] = Field(default=None, validation_alias=AliasChoices("metadata", "meta"))

class SensorOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    location: Optional[str] = None
    serial_number: Optional[str] = None   # newly added field
    meta: Optional[dict] = None
    house_id: Optional[str] = None
    householder: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ConfigCreate(BaseModel):
    data: dict
    revision: Optional[int] = None

class ConfigOut(BaseModel):
    id: int
    sensor_id: uuid.UUID
    revision: int
    data: dict
    created_at: str
    model_config = ConfigDict(from_attributes=True)

class ReadingCreate(BaseModel):
    sensor_id: uuid.UUID
    value: float
    attributes: Optional[dict[str, Any]] = None
    ts: Optional[str] = None

class ReadingOut(BaseModel):
    id: int
    sensor_id: uuid.UUID
    ts: Any
    value: float
    attributes: Optional[dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)

class RegisterIn(BaseModel):
    serial_number: str = Field(min_length=1, pattern=r"^[A-Za-z0-9-]+$")
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str = Field(min_length=3)
    email: EmailStr
    address: str = Field(min_length=1)
    zone: Literal["N", "S", "W", "E", "C"]

class RegisterOut(BaseModel):
    house_id: str

class LoginRequest(BaseModel):
    house_id: str

class HouseholdOut(BaseModel):
    id: int
    house_id: str
    householder: str
    phone: str
    email: EmailStr
    address: str
    zone: str
    model_config = ConfigDict(from_attributes=True)
