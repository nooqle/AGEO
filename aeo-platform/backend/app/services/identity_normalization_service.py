from __future__ import annotations

import re


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def normalize_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    digits = re.sub(r"\D+", "", phone)
    if digits.startswith("0086"):
        digits = digits[4:]
    elif digits.startswith("86") and len(digits) > 11:
        digits = digits[2:]
    return digits or None
