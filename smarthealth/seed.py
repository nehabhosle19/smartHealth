"""Demo data: one district, eight facilities, 30 days of history with deliberate problems.

Run:  python -m smarthealth.manage seed-demo   (refused when SMARTHEALTH_ENV=production)
Passwords are random and printed once (or set SMARTHEALTH_DEMO_PASSWORD for a fixed one).
"""
from __future__ import annotations

import random
import secrets
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import (
    BedStatus, DoctorAttendance, Facility, Footfall, Medicine, StockLog, TestAvailability, User,
)
from .security import hash_password

DISTRICT = "Demo District"
# name, type, lat, lon, beds
FACILITIES = [
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


def seed(db: Session, today: date, days: int = 30, password: str | None = None,
         seed_value: int = 7) -> dict[str, str]:
    """Populate the database; returns {username: password}. Refuses to seed twice."""
    if db.scalar(select(Facility.id).limit(1)) is not None:
        raise RuntimeError("database already contains data")
    rng = random.Random(seed_value)
    iters = config.PBKDF2_ITERATIONS
    creds: dict[str, str] = {}

    def add_user(username: str, role: str, facility_id: int | None) -> None:
        pw = password or secrets.token_urlsafe(9)
        creds[username] = pw
        db.add(User(username=username, password_hash=hash_password(pw, iters),
                    role=role, facility_id=facility_id))

    facilities = [Facility(name=n, type=t, district=DISTRICT, lat=la, lon=lo)
                  for n, t, la, lo, _ in FACILITIES]
    meds = [Medicine(name=n, unit=u) for n, u, _ in MEDICINES]
    db.add_all(facilities + meds)
    db.flush()

    add_user("admin", "admin", None)
    for f in facilities:
        add_user("staff" + str(f.id), "staff", f.id)

    for idx, f in enumerate(facilities):
        beds_total = FACILITIES[idx][4]
        scale = 3.0 if f.type == "CHC" else 1.0
        for mi, m in enumerate(meds):
            base = MEDICINES[mi][2] * scale * rng.uniform(0.8, 1.2)
            stock = base * (45 if idx in (0, 4) else 18)  # CHC Rampur/Malihabad over-stocked
            if idx == 2 and mi in (0, 2):
                stock = base * 4                           # Bakshi running low
            if idx == 5 and mi in (1, 3, 4):
                stock = base * 2                           # Gosainganj near stock-out
            history = []
            for d in range(days - 1, -1, -1):
                use = max(0, round(rng.gauss(base, base * 0.12) * (1 + 0.012 * (days - d))))
                history.append((today - timedelta(days=d), use))
            # work backwards so today's closing stock equals the scenario stock
            closing = round(stock)
            rows = []
            for day, use in reversed(history):
                rows.append(StockLog(facility_id=f.id, medicine_id=m.id, day=day,
                                     closing_qty=max(0, closing), consumed=use))
                closing += use
            db.add_all(rows)

        for d in range(days):
            day = today - timedelta(days=d)
            surge = 1.8 if (idx == 3 and d < 3) else 1.0
            db.add(Footfall(facility_id=f.id, day=day,
                            patients=round(rng.gauss(60 * scale, 8) * surge)))
            if d < 7:
                occ = beds_total if idx == 3 else round(beds_total * rng.uniform(0.4, 0.8))
                db.add(BedStatus(facility_id=f.id, day=day, total=beds_total, occupied=occ))
                for doc in DOCTORS[: 3 if f.type == "CHC" else 2]:
                    absent = idx in (1, 6) and rng.random() < 0.65
                    db.add(DoctorAttendance(facility_id=f.id, doctor_name=doc, day=day,
                                            present=not absent))
        for ti, test in enumerate(TESTS):
            ok = not (idx in (1, 5) and ti >= 1) and not (idx == 2 and ti == 0)
            db.add(TestAvailability(facility_id=f.id, test_name=test, available=ok,
                                    audited_on=today))
    db.commit()
    return creds


if __name__ == "__main__":
    import sys

    from .manage import main

    sys.exit(main(["seed-demo"]))
