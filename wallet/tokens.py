"""
Token and NFT registry.
Add new assets here — no other code changes needed.

Token types:
  "native"  — denom is the on-chain denom string (e.g. "inj")
  "factory" — denom is a factory denom (e.g. "factory/inj.../...")
  "cw20"    — contract is the CW20 contract address

NFT type:
  "cw721"   — contract is the CW721 contract address
"""

TOKENS: dict[str, dict] = {
    "INJ": {
        "type": "native",
        "denom": "inj",
        "decimals": 18,
        "display": "INJ",
    },
    "USDC": {
        "type": "native",
        "denom": "peggy0xA0C59fF5a080D2b954d0c75e46E22a0c371235a",
        "decimals": 6,
        "display": "USDC",
    },
    "XIII": {
        "type": "factory",
        "denom": "factory/inj18flmwwaxxqj8m8l5zl8xhjrnah98fcjp3gcy3e/XIII",
        "decimals": 6,
        "display": "XIII",
    },
}

NFTS: dict[str, dict] = {
    "MASKED": {
        "contract": "",  # TODO: add Masked NFT CW721 contract address
        "display": "Masked",
    },
}


def resolve_token(symbol: str) -> dict | None:
    """Case-insensitive lookup in TOKENS."""
    return next(
        (v for k, v in TOKENS.items() if k.upper() == symbol.upper()),
        None,
    )


def resolve_nft(name: str) -> dict | None:
    """Case-insensitive lookup in NFTS. Returns None if contract not set."""
    entry = next(
        (v for k, v in NFTS.items() if k.upper() == name.upper()),
        None,
    )
    if entry and not entry.get("contract"):
        return None
    return entry
