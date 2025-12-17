"""
utils.py
Validation, dates, exports, sample data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import pandas as pd

import db
from models import PLAN_MONTHS


def today_iso() -> str:
    return date.today().isoformat()


def parse_iso(d: str) -> date:
    return date.fromisoformat(d)


def add_months(start: date, months: int) -> date:
    """
    Add months while keeping day in valid range (e.g., Jan 31 + 1 month => Feb 28/29).
    """
    y = start.year + (start.month - 1 + months) // 12
    m = (start.month - 1 + months) % 12 + 1
    # last day of target month
    if m == 12:
        next_month = date(y + 1, 1, 1)
    else:
        next_month = date(y, m + 1, 1)
    last_day = next_month - timedelta(days=1)
    day = min(start.day, last_day.day)
    return date(y, m, day)


def calc_end_date(start_date_iso: str, plan_type: str) -> str:
    start = parse_iso(start_date_iso)
    months = PLAN_MONTHS.get(plan_type, 1)
    end = add_months(start, months)
    return end.isoformat()


def infer_status(end_date_iso: str) -> str:
    return "active" if parse_iso(end_date_iso) >= date.today() else "expired"


def validate_member_inputs(full_name: str, phone: str, plan_price, start_date: str, end_date: str) -> list[str]:
    errors: list[str] = []
    if not full_name.strip():
        errors.append("Full name is required.")
    if not phone.strip():
        errors.append("Phone is required.")
    try:
        float(plan_price)
    except Exception:
        errors.append("Plan price must be numeric.")
    try:
        sd = parse_iso(start_date)
        ed = parse_iso(end_date)
        if ed <= sd:
            errors.append("End date must be after start date.")
    except Exception:
        errors.append("Start/end dates must be valid ISO dates (YYYY-MM-DD).")
    return errors


def members_to_csv_bytes(rows) -> bytes:
    df = pd.DataFrame([dict(r) for r in rows])
    return df.to_csv(index=False).encode("utf-8")


def payments_to_csv_bytes(rows) -> bytes:
    df = pd.DataFrame([dict(r) for r in rows])
    return df.to_csv(index=False).encode("utf-8")


def revenue_summary_by_month() -> pd.DataFrame:
    rows = db.fetch_all(
        """
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS revenue
        FROM payments
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month DESC
        """
    )
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return pd.DataFrame(columns=["month", "revenue"])
    return df


def insert_sample_data() -> None:
    """
    Insert 3 members and a few payments (safe to run multiple times: adds new rows each time).
    """
    today = date.today()
    join = today.isoformat()

    # Member 1: active, expires in ~5 days
    m1_start = today.replace(day=max(1, today.day - 25)).isoformat()
    m1_end = (today + timedelta(days=5)).isoformat()

    # Member 2: active, longer plan
    m2_start = today.replace(day=max(1, today.day - 10)).isoformat()
    m2_end = calc_end_date(m2_start, "3 months")

    # Member 3: expired
    m3_start = (today - timedelta(days=60)).isoformat()
    m3_end = (today - timedelta(days=2)).isoformat()

    members = [
        ("Ahmed Hassan", "01000000001", "12345678901234", join, "1 month", 300.0, m1_start, m1_end, infer_status(m1_end)),
        ("Mona Ali", "01000000002", None, join, "3 months", 800.0, m2_start, m2_end, infer_status(m2_end)),
        ("Omar Samy", "01000000003", None, join, "1 month", 300.0, m3_start, m3_end, infer_status(m3_end)),
    ]

    ids = []
    for m in members:
        mid = db.execute(
            """
            INSERT INTO members(full_name, phone, national_id, join_date, plan_type, plan_price, start_date, end_date, status)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            m,
        )
        ids.append(mid)

    # Payments
    payments = [
        (ids[0], 300.0, today.isoformat(), "cash", "Sample payment"),
        (ids[1], 800.0, today.isoformat(), "card", "3-month plan paid"),
        (ids[2], 300.0, (today - timedelta(days=60)).isoformat(), "transfer", "Old payment"),
    ]
    db.executemany(
        "INSERT INTO payments(member_id, amount, date, method, notes) VALUES(?,?,?,?,?)",
        payments,
    )
