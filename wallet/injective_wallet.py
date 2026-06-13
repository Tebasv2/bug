import os
import aiohttp
from decimal import Decimal
from pyinjective.core.network import Network
from pyinjective.async_client import AsyncClient
from pyinjective.transaction import Transaction
from pyinjective.wallet import PrivateKey
from pyinjective.proto.cosmos.bank.v1beta1 import tx_pb2 as bank_tx_pb
from pyinjective.proto.cosmos.base.v1beta1 import coin_pb2
from .crypto import encrypt_private_key, decrypt_private_key


INJ_DECIMALS = 18
MIN_GAS_RESERVE = Decimal("0.01")
GAS_LIMIT = 100_000
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
    client = AsyncClient(network)
    await client.sync_timeout_height()

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
        .with_timeout_height(client.timeout_height)
    )

    sign_doc = tx.get_sign_doc(pub_key)
    sig = private_key.sign(sign_doc.SerializeToString())
    tx_raw_bytes = tx.get_tx_data(sig, pub_key)

    resp = await client.broadcast_tx_sync_mode(tx_raw_bytes)
    tx_hash = resp.tx_response.txhash
    if resp.tx_response.code != 0:
        raise RuntimeError(f"Transaction failed: {resp.tx_response.raw_log}")
    return tx_hash
