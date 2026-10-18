"""Request validation models. Every field is bounded to reject absurd or hostile input."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Dated(Strict):
    day: date | None = None  # defaults to today; range-checked against the app clock in the router


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StockIn(_Dated):
    medicine_id: int = Field(gt=0)
    closing_qty: int = Field(ge=0, le=10_000_000)
    consumed: int = Field(ge=0, le=10_000_000)


class FootfallIn(_Dated):
    patients: int = Field(ge=0, le=100_000)


class BedsIn(_Dated):
    total: int = Field(ge=0, le=5_000)
    occupied: int = Field(ge=0, le=5_000)

    @model_validator(mode="after")
    def occupied_within_total(self):
        if self.occupied > self.total:
            raise ValueError("occupied beds cannot exceed total beds")
        return self


class AttendanceIn(_Dated):
    doctor_name: str = Field(min_length=1, max_length=100)
    present: bool


class TestAuditIn(Strict):
    test_name: str = Field(min_length=1, max_length=80)
    available: bool
