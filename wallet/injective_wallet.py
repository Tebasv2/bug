import os
import base64
import json
import random
import aiohttp
from decimal import Decimal
from pyinjective.core.network import Network
from pyinjective.transaction import Transaction
from pyinjective.wallet import PrivateKey
from pyinjective.proto.cosmos.bank.v1beta1 import tx_pb2 as bank_tx_pb
from pyinjective.proto.cosmos.base.v1beta1 import coin_pb2
from pyinjective.proto.cosmwasm.wasm.v1 import tx_pb2 as wasm_tx_pb
from .crypto import encrypt_private_key, decrypt_private_key


INJ_DECIMALS = 18
MIN_GAS_RESERVE = Decimal("0.01")
GAS_LIMIT = 150_000
GAS_PRICE = 500_000_000  # 0.5 gwei in inj


def _get_network() -> Network:
    net = os.environ.get("INJECTIVE_NETWORK", "testnet").lower()
    return Network.testnet() if net == "testnet" else Network.mainnet()


def create_wallet() -> tuple[str, str, str, str]:
    """Returns (address, encrypted_private_key, private_key_hex, mnemonic)."""
    result = PrivateKey.generate()
    if isinstance(result, tuple):
        mnemonic = next((r for r in result if isinstance(r, str)), "")
        private_key = next(r for r in result if not isinstance(r, str))
    else:
        mnemonic = ""
        private_key = result
    pub_key = private_key.to_public_key()
    address = pub_key.to_address()
    private_key_hex = private_key.to_hex()
    encrypted = encrypt_private_key(private_key_hex)
    return address.to_acc_bech32(), encrypted, private_key_hex, mnemonic


async def _lcd_get(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.json()


async def get_balance(address: str) -> Decimal:
    """Returns INJ balance as human-readable Decimal."""
    network = _get_network()
    data = await _lcd_get(f"{network.lcd_endpoint}/cosmos/bank/v1beta1/balances/{address}/by_denom?denom=inj")
    raw = int(data.get("balance", {}).get("amount", "0"))
    return Decimal(raw) / Decimal(10 ** INJ_DECIMALS)


async def _fetch_account_info(address: str) -> tuple[int, int]:
    """Returns (sequence, account_number) via LCD REST."""
    network = _get_network()
    data = await _lcd_get(f"{network.lcd_endpoint}/cosmos/auth/v1beta1/accounts/{address}")
    acc = data.get("account", {})
    base = acc.get("base_account", acc)
    return int(base.get("sequence", 0)), int(base.get("account_number", 0))


async def send_inj(
    encrypted_sender_key: str,
    receiver_address: str,
    amount: Decimal,
) -> str:
    """Broadcasts an INJ transfer. Returns tx hash."""
    network = _get_network()

    private_key = PrivateKey.from_hex(decrypt_private_key(encrypted_sender_key))
    pub_key = private_key.to_public_key()
    address = pub_key.to_address()
    acc_bech32 = address.to_acc_bech32()

    sequence, account_number = await _fetch_account_info(acc_bech32)

    # Convert to smallest unit (attoINJ)
    amount_wei = str(int(amount * Decimal(10 ** INJ_DECIMALS)))
    fee_wei = str(GAS_PRICE * GAS_LIMIT)

    # Build MsgSend directly from protobuf — bypasses Composer token registry
    msg = bank_tx_pb.MsgSend(
        from_address=acc_bech32,
        to_address=receiver_address,
        amount=[coin_pb2.Coin(denom="inj", amount=amount_wei)],
    )

    fee = [coin_pb2.Coin(denom="inj", amount=fee_wei)]

    tx = (
        Transaction()
        .with_messages(msg)
        .with_sequence(sequence)
        .with_account_num(account_number)
        .with_chain_id(network.chain_id)
        .with_gas(GAS_LIMIT)
        .with_fee(fee)
        .with_memo("")
        .with_timeout_height(0)
    )

    sign_doc = tx.get_sign_doc(pub_key)
    sig = private_key.sign(sign_doc.SerializeToString())
    tx_raw_bytes = tx.get_tx_data(sig, pub_key)

    tx_b64 = base64.b64encode(tx_raw_bytes).decode()

    # Try multiple LCD endpoints — testnet nodes can have mempool bugs
    lcd_endpoints = [
        network.lcd_endpoint,
        "https://testnet.sentry.lcd.injective.network",
        "https://k8s.testnet.lcd.injective.network",
    ] if "testnet" in (os.environ.get("INJECTIVE_NETWORK", "testnet")) else [
        network.lcd_endpoint,
        "https://lcd.injective.network",
        "https://sentry.lcd.injective.network",
    ]

    last_error = None
    async with aiohttp.ClientSession() as session:
        for lcd in lcd_endpoints:
            try:
                async with session.post(
                    f"{lcd}/cosmos/tx/v1beta1/txs",
                    json={"tx_bytes": tx_b64, "mode": "BROADCAST_MODE_ASYNC"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    result = await r.json()

                tx_response = result.get("tx_response", result)
                code = int(tx_response.get("code", 0))
                if code not in (0, 19):  # 19 = already in mempool (ok)
                    last_error = f"code {code}: {tx_response.get('raw_log', result)}"
                    continue
                tx_hash = tx_response.get("txhash") or tx_response.get("tx_hash") or tx_response.get("hash", "")
                if tx_hash:
                    return tx_hash
            except Exception as e:
                last_error = str(e)
                continue

    raise RuntimeError(f"All broadcast endpoints failed. Last error: {last_error}")


async def _broadcast(tx_raw_bytes: bytes, network: Network) -> str:
    """Broadcast a signed tx and return the tx hash."""
    tx_b64 = base64.b64encode(tx_raw_bytes).decode()
    is_testnet = "testnet" in os.environ.get("INJECTIVE_NETWORK", "testnet")
    lcd_endpoints = (
        [network.lcd_endpoint,
         "https://testnet.sentry.lcd.injective.network",
         "https://k8s.testnet.lcd.injective.network"]
        if is_testnet else
        [network.lcd_endpoint,
         "https://lcd.injective.network",
         "https://sentry.lcd.injective.network"]
    )
    last_error = None
    async with aiohttp.ClientSession() as session:
        for lcd in lcd_endpoints:
            try:
                async with session.post(
                    f"{lcd}/cosmos/tx/v1beta1/txs",
                    json={"tx_bytes": tx_b64, "mode": "BROADCAST_MODE_ASYNC"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    result = await r.json()
                tx_response = result.get("tx_response", result)
                code = int(tx_response.get("code", 0))
                if code not in (0, 19):
                    last_error = f"code {code}: {tx_response.get('raw_log', result)}"
                    continue
                tx_hash = tx_response.get("txhash") or tx_response.get("tx_hash") or tx_response.get("hash", "")
                if tx_hash:
                    return tx_hash
            except Exception as e:
                last_error = str(e)
                continue
    raise RuntimeError(f"All broadcast endpoints failed. Last error: {last_error}")


def _build_and_sign(msg, private_key, pub_key, sequence: int, account_number: int, network: Network) -> bytes:
    fee = [coin_pb2.Coin(denom="inj", amount=str(GAS_PRICE * GAS_LIMIT))]
    tx = (
        Transaction()
        .with_messages(msg)
        .with_sequence(sequence)
        .with_account_num(account_number)
        .with_chain_id(network.chain_id)
        .with_gas(GAS_LIMIT)
        .with_fee(fee)
        .with_memo("")
        .with_timeout_height(0)
    )
    sign_doc = tx.get_sign_doc(pub_key)
    sig = private_key.sign(sign_doc.SerializeToString())
    return tx.get_tx_data(sig, pub_key)


async def send_token(encrypted_sender_key: str, receiver_address: str, amount: Decimal, token: dict) -> str:
    """Send a CW20, factory, or native token. Returns tx hash."""
    network = _get_network()
    private_key = PrivateKey.from_hex(decrypt_private_key(encrypted_sender_key))
    pub_key = private_key.to_public_key()
    acc_bech32 = pub_key.to_address().to_acc_bech32()
    sequence, account_number = await _fetch_account_info(acc_bech32)

    token_type = token["type"]
    decimals = token.get("decimals", 18)
    amount_raw = str(int(amount * Decimal(10 ** decimals)))

    if token_type in ("native", "factory"):
        msg = bank_tx_pb.MsgSend(
            from_address=acc_bech32,
            to_address=receiver_address,
            amount=[coin_pb2.Coin(denom=token["denom"], amount=amount_raw)],
        )
    elif token_type == "cw20":
        execute_msg = json.dumps({"transfer": {"recipient": receiver_address, "amount": amount_raw}}).encode()
        msg = wasm_tx_pb.MsgExecuteContract(
            sender=acc_bech32,
            contract=token["contract"],
            msg=execute_msg,
        )
    else:
        raise ValueError(f"Unknown token type: {token_type}")

    tx_raw_bytes = _build_and_sign(msg, private_key, pub_key, sequence, account_number, network)
    return await _broadcast(tx_raw_bytes, network)


async def get_nft_tokens(owner_address: str, contract: str) -> list[str]:
    """Returns list of token_ids owned by address in a CW721 contract."""
    network = _get_network()
    query = base64.b64encode(json.dumps({"tokens": {"owner": owner_address, "limit": 50}}).encode()).decode()
    data = await _lcd_get(f"{network.lcd_endpoint}/cosmwasm/wasm/v1/contract/{contract}/smart/{query}")
    return data.get("data", {}).get("ids", [])


async def send_nft(encrypted_sender_key: str, receiver_address: str, contract: str) -> tuple[str, str]:
    """Send a random NFT from sender's wallet. Returns (token_id, tx_hash)."""
    network = _get_network()
    private_key = PrivateKey.from_hex(decrypt_private_key(encrypted_sender_key))
    pub_key = private_key.to_public_key()
    acc_bech32 = pub_key.to_address().to_acc_bech32()

    token_ids = await get_nft_tokens(acc_bech32, contract)
    if not token_ids:
        raise RuntimeError("You don't own any NFTs from this collection.")

    token_id = random.choice(token_ids)
    sequence, account_number = await _fetch_account_info(acc_bech32)

    execute_msg = json.dumps({"transfer_nft": {"recipient": receiver_address, "token_id": token_id}}).encode()
    msg = wasm_tx_pb.MsgExecuteContract(
        sender=acc_bech32,
        contract=contract,
        msg=execute_msg,
    )

    tx_raw_bytes = _build_and_sign(msg, private_key, pub_key, sequence, account_number, network)
    tx_hash = await _broadcast(tx_raw_bytes, network)
    return token_id, tx_hash
