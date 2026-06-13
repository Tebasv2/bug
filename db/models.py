import uuid
from sqlalchemy import Column, String, BigInteger, DateTime, Numeric
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone


class Base(DeclarativeBase):
    pass


class Wallet(Base):
    __tablename__ = "wallets"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True, index=True)
    address = Column(String, nullable=False, unique=True)
    encrypted_private_key = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TipTransaction(Base):
    __tablename__ = "tip_transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tx_hash = Column(String, nullable=True)
    sender_user_id = Column(BigInteger, nullable=False)
    receiver_user_id = Column(BigInteger, nullable=False)
    amount = Column(Numeric(precision=36, scale=18), nullable=False)
    denom = Column(String, default="inj")
    chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
