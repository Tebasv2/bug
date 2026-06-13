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
    # Add more tokens below, e.g.:
    # "XIII": {
    #     "type": "cw20",
    #     "contract": "inj1...",
    #     "decimals": 6,
    #     "display": "XIII",
    # },
    # "USDT": {
    #     "type": "factory",
    #     "denom": "factory/inj.../usdt",
    #     "decimals": 6,
    #     "display": "USDT",
    # },
}

NFTS: dict[str, dict] = {
    # Add NFT collections below, e.g.:
    # "MASKED": {
    #     "contract": "inj1...",
    #     "display": "Masked",
    # },
}


def resolve_token(symbol: str) -> dict | None:
    """Case-insensitive lookup in TOKENS."""
    return next(
        (v for k, v in TOKENS.items() if k.upper() == symbol.upper()),
        None,
    )


def resolve_nft(name: str) -> dict | None:
    """Case-insensitive lookup in NFTS."""
    return next(
        (v for k, v in NFTS.items() if k.upper() == name.upper()),
        None,
    )
