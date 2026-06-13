from decimal import Decimal
from sqlalchemy import select, func, desc
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
    denom: str = "inj",
) -> TipTransaction:
    tx = TipTransaction(
        tx_hash=tx_hash,
        sender_user_id=sender_id,
        receiver_user_id=receiver_id,
        amount=amount,
        denom=denom,
        chat_id=chat_id,
    )
    session.add(tx)
    await session.commit()
    return tx


async def get_user_history(
    session: AsyncSession, user_id: int, limit: int = 10
) -> tuple[list[TipTransaction], list[TipTransaction]]:
    """Returns (sent, received) tip lists."""
    sent = (await session.execute(
        select(TipTransaction)
        .where(TipTransaction.sender_user_id == user_id)
        .order_by(desc(TipTransaction.created_at))
        .limit(limit)
    )).scalars().all()

    received = (await session.execute(
        select(TipTransaction)
        .where(TipTransaction.receiver_user_id == user_id)
        .order_by(desc(TipTransaction.created_at))
        .limit(limit)
    )).scalars().all()

    return list(sent), list(received)


async def get_group_leaderboard(
    session: AsyncSession, chat_id: int, limit: int = 10
) -> list[tuple[int, Decimal]]:
    """Returns list of (sender_user_id, total_sent) sorted by total desc."""
    rows = (await session.execute(
        select(TipTransaction.sender_user_id, func.sum(TipTransaction.amount).label("total"))
        .where(TipTransaction.chat_id == chat_id)
        .group_by(TipTransaction.sender_user_id)
        .order_by(desc("total"))
        .limit(limit)
    )).all()
    return [(r.sender_user_id, Decimal(str(r.total))) for r in rows]


async def get_wallet_by_user_ids(
    session: AsyncSession, user_ids: list[int]
) -> dict[int, Wallet]:
    rows = (await session.execute(
        select(Wallet).where(Wallet.user_id.in_(user_ids))
    )).scalars().all()
    return {w.user_id: w for w in rows}
