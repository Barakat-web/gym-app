"""
models.py
Lightweight domain helpers (plans, dataclasses).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date

# Plan durations in months (used for end_date auto-calculation)
PLAN_MONTHS = {
    "1 month": 1,
    "3 months": 3,
    "6 months": 6,
    "12 months": 12,
}


@dataclass(frozen=True)
class Member:
    id: int | None
    full_name: str
    phone: str
    national_id: str | None
    join_date: str
    plan_type: str
    plan_price: float
    start_date: str
    end_date: str
    status: str  # 'active' or 'expired'


@dataclass(frozen=True)
class Payment:
    id: int | None
    member_id: int
    amount: float
    date: str
    method: str  # cash/card/transfer
    notes: str | None
