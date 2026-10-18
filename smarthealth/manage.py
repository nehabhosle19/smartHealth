"""Administration CLI: bootstrap a real deployment without any default credentials.

    python -m smarthealth.manage create-admin --username district.admin
    python -m smarthealth.manage add-facility --name "PHC Rampur" --type PHC --district Sitapur --lat 27.5 --lon 80.7
    python -m smarthealth.manage add-medicine --name "Paracetamol 500mg" --unit tablets
    python -m smarthealth.manage create-staff --username rampur.staff --facility-id 1
    python -m smarthealth.manage set-password --username rampur.staff
    python -m smarthealth.manage deactivate --username rampur.staff
    python -m smarthealth.manage seed-demo        # fake data; refused in production

Passwords are read from a hidden prompt, or from SMARTHEALTH_PASSWORD for automation.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import make_engine, make_session_factory
from .models import Base, Facility, Medicine, User
from .security import hash_password

USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,64}$")


class CliError(Exception):
    """A user-facing error: printed without a traceback."""


def check_password(password: str) -> None:
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise CliError(f"password must be at least {config.MIN_PASSWORD_LENGTH} characters")
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise CliError("password must mix upper- and lower-case letters and include a digit")


def _new_user(db: Session, username: str, password: str, role: str, facility_id: int | None) -> User:
    if not USERNAME_RE.match(username):
        raise CliError("username must be 3-64 characters: letters, digits, . _ @ -")
    check_password(password)
    if db.scalar(select(User.id).where(User.username == username)):
        raise CliError(f"user '{username}' already exists")
    if facility_id is not None and db.get(Facility, facility_id) is None:
        raise CliError(f"facility {facility_id} does not exist")
    user = User(username=username, role=role, facility_id=facility_id, is_active=True,
                password_hash=hash_password(password, config.PBKDF2_ITERATIONS))
    db.add(user)
    db.commit()
    return user


def create_admin(db: Session, username: str, password: str) -> User:
    return _new_user(db, username, password, "admin", None)


def create_staff(db: Session, username: str, password: str, facility_id: int) -> User:
    return _new_user(db, username, password, "staff", facility_id)


def add_facility(db: Session, name: str, type_: str, district: str, lat: float, lon: float) -> Facility:
    if type_ not in ("PHC", "CHC"):
        raise CliError("type must be PHC or CHC")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise CliError("latitude/longitude out of range")
    if db.scalar(select(Facility.id).where(Facility.name == name)):
        raise CliError(f"facility '{name}' already exists")
    facility = Facility(name=name, type=type_, district=district, lat=lat, lon=lon)
    db.add(facility)
    db.commit()
    return facility


def add_medicine(db: Session, name: str, unit: str) -> Medicine:
    if db.scalar(select(Medicine.id).where(Medicine.name == name)):
        raise CliError(f"medicine '{name}' already exists")
    medicine = Medicine(name=name, unit=unit)
    db.add(medicine)
    db.commit()
    return medicine


def _get_user(db: Session, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise CliError(f"no such user '{username}'")
    return user


def set_password(db: Session, username: str, password: str) -> None:
    """Changing the hash also invalidates the user's existing sessions."""
    check_password(password)
    _get_user(db, username).password_hash = hash_password(password, config.PBKDF2_ITERATIONS)
    db.commit()


def set_active(db: Session, username: str, active: bool) -> None:
    _get_user(db, username).is_active = active
    db.commit()


def _read_password(confirm: bool = True) -> str:
    env = os.getenv("SMARTHEALTH_PASSWORD")
    if env:
        return env
    first = getpass.getpass("Password: ")
    if confirm and first != getpass.getpass("Repeat password: "):
        raise CliError("passwords do not match")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smarthealth.manage", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="create tables directly (development; production uses alembic)")
    p = sub.add_parser("create-admin"); p.add_argument("--username", required=True)
    p = sub.add_parser("create-staff"); p.add_argument("--username", required=True)
    p.add_argument("--facility-id", type=int, required=True)
    p = sub.add_parser("add-facility"); p.add_argument("--name", required=True)
    p.add_argument("--type", required=True, choices=["PHC", "CHC"]); p.add_argument("--district", required=True)
    p.add_argument("--lat", type=float, required=True); p.add_argument("--lon", type=float, required=True)
    p = sub.add_parser("add-medicine"); p.add_argument("--name", required=True); p.add_argument("--unit", required=True)
    p = sub.add_parser("set-password"); p.add_argument("--username", required=True)
    p = sub.add_parser("deactivate"); p.add_argument("--username", required=True)
    p = sub.add_parser("activate"); p.add_argument("--username", required=True)
    sub.add_parser("list-facilities")
    sub.add_parser("seed-demo", help="load fake demo data (refused in production)")
    args = parser.parse_args(argv)

    engine = make_engine()
    try:
        if args.cmd == "init-db":
            Base.metadata.create_all(engine)
            print("tables created")
            return 0
        with make_session_factory(engine)() as db:
            if args.cmd == "create-admin":
                create_admin(db, args.username, _read_password()); print("admin created")
            elif args.cmd == "create-staff":
                create_staff(db, args.username, _read_password(), args.facility_id); print("staff user created")
            elif args.cmd == "add-facility":
                f = add_facility(db, args.name, args.type, args.district, args.lat, args.lon)
                print(f"facility created with id {f.id}")
            elif args.cmd == "add-medicine":
                m = add_medicine(db, args.name, args.unit); print(f"medicine created with id {m.id}")
            elif args.cmd == "set-password":
                set_password(db, args.username, _read_password()); print("password updated; sessions revoked")
            elif args.cmd in ("deactivate", "activate"):
                set_active(db, args.username, args.cmd == "activate"); print(f"user {args.cmd}d")
            elif args.cmd == "list-facilities":
                for f in db.scalars(select(Facility).order_by(Facility.id)):
                    print(f"{f.id:4d}  {f.type}  {f.name}  ({f.district})")
            elif args.cmd == "seed-demo":
                if config.IS_PROD:
                    raise CliError("refusing to load demo data when SMARTHEALTH_ENV=production")
                from .seed import seed
                Base.metadata.create_all(engine)
                for user, pw in seed(db, config.local_today(),
                                     password=os.getenv("SMARTHEALTH_DEMO_PASSWORD")).items():
                    print(f"{user:10s} {pw}")
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
