"""SQLAlchemy ORM models."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql.expression import true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(3))  # PHC | CHC
    district: Mapped[str] = mapped_column(String(80), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(10))  # admin | staff
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    unit: Mapped[str] = mapped_column(String(20))


class StockLog(Base):
    """Daily closing stock and consumption of one medicine at one facility."""

    __tablename__ = "stock_logs"
    __table_args__ = (UniqueConstraint("facility_id", "medicine_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    closing_qty: Mapped[int] = mapped_column(Integer)
    consumed: Mapped[int] = mapped_column(Integer)


class Footfall(Base):
    __tablename__ = "footfall"
    __table_args__ = (UniqueConstraint("facility_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    patients: Mapped[int] = mapped_column(Integer)


class BedStatus(Base):
    __tablename__ = "bed_status"
    __table_args__ = (UniqueConstraint("facility_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    total: Mapped[int] = mapped_column(Integer)
    occupied: Mapped[int] = mapped_column(Integer)


class DoctorAttendance(Base):
    __tablename__ = "doctor_attendance"
    __table_args__ = (UniqueConstraint("facility_id", "doctor_name", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    doctor_name: Mapped[str] = mapped_column(String(100))
    day: Mapped[date] = mapped_column(Date, index=True)
    present: Mapped[bool] = mapped_column(Boolean)


class TestAvailability(Base):
    """Latest audit result per diagnostic test at a facility."""

    __tablename__ = "test_availability"
    __table_args__ = (UniqueConstraint("facility_id", "test_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), index=True)
    test_name: Mapped[str] = mapped_column(String(80))
    available: Mapped[bool] = mapped_column(Boolean)
    audited_on: Mapped[date] = mapped_column(Date)
