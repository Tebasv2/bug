import os
import aiohttp
from decimal import Decimal
from pyinjective.core.network import Network
from pyinjective.async_client import AsyncClient
from pyinjective.transaction import Transaction
from pyinjective.wallet import PrivateKey
from pyinjective.composer import Composer
from .crypto import encrypt_private_key, decrypt_private_key


INJ_DECIMALS = 18
MIN_GAS_RESERVE = Decimal("0.01")


def _get_network() -> Network:
    net = os.environ.get("INJECTIVE_NETWORK", "testnet").lower()
    return Network.testnet() if net == "testnet" else Network.mainnet()


def _lcd_endpoint(network: Network) -> str:
    return network.lcd_endpoint


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
    lcd = _lcd_endpoint(network)
    data = await _lcd_get(f"{lcd}/cosmos/bank/v1beta1/balances/{address}/by_denom?denom=inj")
    raw = int(data.get("balance", {}).get("amount", "0"))
    return Decimal(raw) / Decimal(10 ** INJ_DECIMALS)


async def _fetch_account_info(address: str) -> tuple[int, int]:
    """Returns (sequence, account_number) via LCD REST."""
    network = _get_network()
    lcd = _lcd_endpoint(network)
    data = await _lcd_get(f"{lcd}/cosmos/auth/v1beta1/accounts/{address}")
    acc = data.get("account", {})
    # Injective wraps in base_account
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
    composer = Composer(network=network.string())
    await client.sync_timeout_height()

    private_key = PrivateKey.from_hex(decrypt_private_key(encrypted_sender_key))
    pub_key = private_key.to_public_key()
    address = pub_key.to_address()
    acc_bech32 = address.to_acc_bech32()

    sequence, account_number = await _fetch_account_info(acc_bech32)

    amount_int = int(amount * Decimal(10 ** INJ_DECIMALS))

    msg = composer.MsgSend(
        from_address=acc_bech32,
        to_address=receiver_address,
        amount=amount_int,
        denom="inj",
    )

    gas_price = 500_000_000
    gas_limit = 100_000
    fee = [composer.coin(amount=gas_price * gas_limit, denom="inj")]

    tx = (
        Transaction()
        .with_messages(msg)
        .with_sequence(sequence)
        .with_account_num(account_number)
        .with_chain_id(network.chain_id)
        .with_gas(gas_limit)
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
