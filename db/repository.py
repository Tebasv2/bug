from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Wallet, TipTransaction


async def get_wallet_by_user_id(session: AsyncSession, user_id: int) -> Wallet | None:
    result = await session.execute(select(Wallet).where(Wallet.user_id == user_id))
    return result.scalar_one_or_none()


async def get_wallet_by_username(session: AsyncSession, username: str) -> Wallet | None:
    result = await session.execute(
        select(Wallet).where(Wallet.username == username.lstrip("@").lower())
    )
    return result.scalar_one_or_none()


async def create_wallet(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    address: str,
    encrypted_private_key: str,
) -> Wallet:
    wallet = Wallet(
        user_id=user_id,
        username=username.lower() if username else None,
        address=address,
        encrypted_private_key=encrypted_private_key,
    )
    session.add(wallet)
    await session.commit()
    return wallet


async def update_username(session: AsyncSession, user_id: int, username: str | None) -> None:
    wallet = await get_wallet_by_user_id(session, user_id)
    if wallet:
        wallet.username = username.lower() if username else None
        await session.commit()


async def save_transaction(
    session: AsyncSession,
    tx_hash: str,
    sender_id: int,
    receiver_id: int,
    amount: str,
    chat_id: int | None,
) -> TipTransaction:
    tx = TipTransaction(
        id=tx_hash,
        sender_user_id=sender_id,
        receiver_user_id=receiver_id,
        amount=amount,
        chat_id=chat_id,
    )
    session.add(tx)
    await session.commit()
    return tx
