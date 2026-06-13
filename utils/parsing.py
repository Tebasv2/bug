import re
from decimal import Decimal, InvalidOperation


# Matches: tip @user 0.1 INJ  |  tip @user 1 XIII  |  tip @user 1 MaskedNFT
TIP_PATTERN = re.compile(
    r"tip\s+@?(\w+)\s+([\d.]+)\s+(\w+)",
    re.IGNORECASE,
)

# NFT-only: tip @user 1 MaskedNFT  (amount ignored but kept for consistency)
NFT_PATTERN = re.compile(
    r"tip\s+@?(\w+)\s+\d+\s+(\w+)",
    re.IGNORECASE,
)


def parse_tip_command(text: str) -> tuple[str, Decimal, str] | None:
    """
    Parses: tip @user 0.1 TOKEN  or  tip @user 1 NFTNAME
    Returns (username, amount, symbol) or None.
    """
    match = TIP_PATTERN.search(text)
    if not match:
        return None
    username = match.group(1).lower()
    symbol = match.group(3).upper()
    try:
        amount = Decimal(match.group(2))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return username, amount, symbol
