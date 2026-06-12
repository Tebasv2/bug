import re
from decimal import Decimal, InvalidOperation


TIP_PATTERN = re.compile(
    r"tip\s+@?(\w+)\s+([\d.]+)\s*(inj)?",
    re.IGNORECASE,
)


def parse_tip_command(text: str) -> tuple[str, Decimal] | None:
    """
    Parses a tip command like: tip @tebas 0.1 INJ
    Returns (username, amount) or None if not matched.
    """
    match = TIP_PATTERN.search(text)
    if not match:
        return None
    username = match.group(1).lower()
    try:
        amount = Decimal(match.group(2))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return username, amount
