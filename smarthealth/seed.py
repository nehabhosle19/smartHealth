"""Demo data: one district, eight facilities, 30 days of history with deliberate problems.

Run:  python -m smarthealth.manage seed-demo   (refused when SMARTHEALTH_ENV=production)
Passwords are random and printed once (or set SMARTHEALTH_DEMO_PASSWORD for a fixed one).
"""
from __future__ import annotations

import random
import re
import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import (
    Base,
    BedStatus,
    DoctorAttendance,
    Facility,
    Footfall,
    Medicine,
    StockLog,
    TestAvailability,
    User,
)
from .security import hash_password, verify_password

DISTRICT = "Demo District"
FACILITIES = [  # name, type, lat, lon, beds
    ("CHC Rampur", "CHC", 26.85, 80.95, 30),
    ("PHC Aliganj", "PHC", 26.90, 80.98, 6),
    ("PHC Bakshi", "PHC", 26.78, 80.90, 6),
    ("PHC Chinhat", "PHC", 26.88, 81.05, 6),
    ("CHC Malihabad", "CHC", 26.92, 80.71, 30),
    ("PHC Gosainganj", "PHC", 26.68, 81.00, 6),
    ("PHC Mohanlal", "PHC", 26.70, 80.80, 6),
    ("PHC Itaunja", "PHC", 27.15, 80.84, 6),
]
MEDICINES = [  # name, unit, typical daily use at a PHC
    ("Paracetamol 500mg", "tablets", 120), ("Amoxicillin 250mg", "capsules", 60),
    ("ORS sachets", "sachets", 40), ("Metformin 500mg", "tablets", 80),
    ("Iron-folic acid", "tablets", 90), ("Oxytocin 10IU", "ampoules", 4),
]
TESTS = ["Malaria RDT", "Hemoglobin", "Blood sugar", "Urine pregnancy", "HIV screening"]
DOCTORS = ["Dr. Sharma", "Dr. Verma", "Dr. Khan"]

# ---- deliberate problems, so the demo shows every feature -------------------------------
DEFAULT_COVER_DAYS = 18
OVERSTOCKED = {"CHC Rampur", "CHC Malihabad"}                     # donors for redistribution
OVERSTOCK_COVER_DAYS = 45
SHORT_STOCK_DAYS = {                                              # (facility, medicine) -> days of cover
    ("PHC Bakshi", "Paracetamol 500mg"): 4, ("PHC Bakshi", "ORS sachets"): 4,
    ("PHC Gosainganj", "Amoxicillin 250mg"): 2, ("PHC Gosainganj", "Metformin 500mg"): 2,
    ("PHC Gosainganj", "Iron-folic acid"): 2,
}
FULL_BEDS = {"PHC Chinhat"}
FOOTFALL_SURGE = {"PHC Chinhat": (1.8, 3)}                        # (multiplier, last N days)
ABSENT_DOCTORS = {"PHC Aliganj", "PHC Mohanlal"}
ABSENCE_RATE = 0.65
MISSING_TESTS = {
    "PHC Aliganj": set(TESTS[1:]), "PHC Gosainganj": set(TESTS[1:]), "PHC Bakshi": {"Malaria RDT"},
}
CHC_SCALE = 3.0           # a CHC serves roughly three PHCs' worth of patients
DAILY_NOISE = 0.12        # stdev of daily consumption relative to its mean
GROWTH_PER_DAY = 0.012    # gentle upward demand trend
HISTORY_DAYS_FOR_BEDS_AND_ATTENDANCE = 7


def _add_users(db: Session, facilities: list[Facility], password: str | None) -> dict[str, str]:
    credentials: dict[str, str] = {}
    accounts = [("admin", "admin", None)] + [(f"staff{f.id}", "staff", f.id) for f in facilities]
    for username, role, facility_id in accounts:
        plain = password or secrets.token_urlsafe(9)
        credentials[username] = plain
        db.add(User(username=username, role=role, facility_id=facility_id,
                    password_hash=hash_password(plain, config.PBKDF2_ITERATIONS)))
    return credentials


def _closing_stock_today(facility: Facility, medicine: Medicine, base_daily_use: float) -> float:
    if (facility.name, medicine.name) in SHORT_STOCK_DAYS:
        return base_daily_use * SHORT_STOCK_DAYS[(facility.name, medicine.name)]
    cover = OVERSTOCK_COVER_DAYS if facility.name in OVERSTOCKED else DEFAULT_COVER_DAYS
    return base_daily_use * cover


def _stock_history(db: Session, rng: random.Random, facility: Facility, medicine: Medicine,
                   daily_use: int, scale: float, today: date, days: int) -> None:
    base = daily_use * scale * rng.uniform(0.8, 1.2)
    usage = [
        (today - timedelta(days=d),
         max(0, round(rng.gauss(base, base * DAILY_NOISE) * (1 + GROWTH_PER_DAY * (days - d)))))
        for d in range(days - 1, -1, -1)
    ]
    closing = round(_closing_stock_today(facility, medicine, base))
    for day, used in reversed(usage):  # walk backwards so today's closing stock hits the scenario
        db.add(StockLog(facility_id=facility.id, medicine_id=medicine.id, day=day,
                        closing_qty=max(0, closing), consumed=used))
        closing += used


def _daily_activity(db: Session, rng: random.Random, facility: Facility, beds_total: int,
                    scale: float, today: date, days: int) -> None:
    surge, surge_days = FOOTFALL_SURGE.get(facility.name, (1.0, 0))
    for d in range(days):
        day = today - timedelta(days=d)
        patients = round(rng.gauss(60 * scale, 8) * (surge if d < surge_days else 1.0))
        db.add(Footfall(facility_id=facility.id, day=day, patients=patients))
        if d < HISTORY_DAYS_FOR_BEDS_AND_ATTENDANCE:
            _beds_and_attendance(db, rng, facility, beds_total, day)


def _beds_and_attendance(db: Session, rng: random.Random, facility: Facility, beds_total: int, day: date) -> None:
    occupied = beds_total if facility.name in FULL_BEDS else round(beds_total * rng.uniform(0.4, 0.8))
    db.add(BedStatus(facility_id=facility.id, day=day, total=beds_total, occupied=occupied))
    for doctor in DOCTORS[: 3 if facility.type == "CHC" else 2]:
        absent = facility.name in ABSENT_DOCTORS and rng.random() < ABSENCE_RATE
        db.add(DoctorAttendance(facility_id=facility.id, doctor_name=doctor, day=day, present=not absent))


def _test_audits(db: Session, facility: Facility, today: date) -> None:
    missing = MISSING_TESTS.get(facility.name, set())
    for test in TESTS:
        db.add(TestAvailability(facility_id=facility.id, test_name=test,
                                available=test not in missing, audited_on=today))


DEMO_USERNAME = re.compile(r"^(admin|staff\d+)$")
DEMO_STALE_AFTER_DAYS = 1  # demo data older than this is regenerated so charts never look abandoned


def _sync_demo_passwords(db: Session, password: str) -> int:
    """Make every demo account use `password`; returns how many were changed."""
    changed = 0
    for user in db.scalars(select(User)):
        if DEMO_USERNAME.match(user.username) and not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password, config.PBKDF2_ITERATIONS)
            changed += 1
    db.commit()
    return changed


def bootstrap_demo(db: Session, today: date, password: str) -> str:
    """Idempotent demo setup for hosts without shell access (set SMARTHEALTH_DEMO_PASSWORD).

    * no data yet, or data older than a day  -> (re)create the demo district from scratch
    * data is current                        -> only make sure the demo password matches
    """
    engine = db.get_bind()
    Base.metadata.create_all(engine)
    latest = db.scalar(select(func.max(StockLog.day)))
    if latest is not None and latest >= today - timedelta(days=DEMO_STALE_AFTER_DAYS):
        return f"demo data is current; {_sync_demo_passwords(db, password)} password(s) updated"

    db.rollback()  # release the connection so DROP TABLE is not blocked by our own transaction
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed(db, today, password=password)
    return f"demo data created for {today.isoformat()}"


def seed(db: Session, today: date, days: int = 30, password: str | None = None,
         seed_value: int = 7) -> dict[str, str]:
    """Populate the database; returns {username: password}. Refuses to seed twice."""
    if db.scalar(select(Facility.id).limit(1)) is not None:
        raise RuntimeError("database already contains data")
    rng = random.Random(seed_value)  # noqa: S311 - deterministic demo data, not security-sensitive

    facilities = [Facility(name=n, type=t, district=DISTRICT, lat=la, lon=lo) for n, t, la, lo, _ in FACILITIES]
    medicines = [Medicine(name=n, unit=u) for n, u, _ in MEDICINES]
    db.add_all(facilities + medicines)
    db.flush()
    credentials = _add_users(db, facilities, password)

    for facility, (*_, beds_total) in zip(facilities, FACILITIES, strict=True):
        scale = CHC_SCALE if facility.type == "CHC" else 1.0
        for medicine, (*_, daily_use) in zip(medicines, MEDICINES, strict=True):
            _stock_history(db, rng, facility, medicine, daily_use, scale, today, days)
        _daily_activity(db, rng, facility, beds_total, scale, today, days)
        _test_audits(db, facility, today)
    db.commit()
    return credentials


if __name__ == "__main__":
    import sys

    from .manage import main

    sys.exit(main(["seed-demo"]))
