from decimal import Decimal
from telegram import Update
from telegram.ext import ContextTypes

from db.database import get_session
from db import repository
from wallet.injective_wallet import create_wallet, get_balance, send_inj, MIN_GAS_RESERVE
from utils.parsing import parse_tip_command


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    async with get_session() as session:
        existing = await repository.get_wallet_by_user_id(session, user.id)
        if existing:
            await update.message.reply_text(
                f"You already have a wallet!\n\n"
                f"Address: `{existing.address}`\n\n"
                f"Use /balance to check your balance.",
                parse_mode="Markdown",
            )
            return

        address, encrypted_key = create_wallet()
        await repository.create_wallet(
            session,
            user_id=user.id,
            username=user.username,
            address=address,
            encrypted_private_key=encrypted_key,
        )

    await update.message.reply_text(
        f"Wallet created! \n\n"
        f"Address: `{address}`\n\n"
        f"Fund it with INJ and you're ready to tip. Use /balance to check your balance.",
        parse_mode="Markdown",
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user.id)

    if not wallet:
        await update.message.reply_text("No wallet found. Use /start to create one.")
        return

    try:
        balance = await get_balance(wallet.address)
        await update.message.reply_text(
            f"Balance: `{balance:.6f} INJ`\nAddress: `{wallet.address}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"Could not fetch balance: {e}")


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user.id)

    if not wallet:
        await update.message.reply_text("No wallet found. Use /start to create one.")
        return

    await update.message.reply_text(
        f"Your wallet address:\n`{wallet.address}`",
        parse_mode="Markdown",
    )


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if len(args) != 2:
        await update.message.reply_text("Usage: /withdraw <address> <amount>\nExample: /withdraw inj1abc... 0.5")
        return

    dest_address, amount_str = args[0], args[1]
    try:
        amount = Decimal(amount_str)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    if amount <= 0:
        await update.message.reply_text("Amount must be positive.")
        return

    if not dest_address.startswith("inj1"):
        await update.message.reply_text("Invalid Injective address (must start with inj1).")
        return

    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user.id)

    if not wallet:
        await update.message.reply_text("No wallet found. Use /start to create one.")
        return

    try:
        balance = await get_balance(wallet.address)
        if balance < amount + MIN_GAS_RESERVE:
            await update.message.reply_text(
                f"Insufficient balance. You have `{balance:.6f} INJ` "
                f"(need {amount} + {MIN_GAS_RESERVE} for gas).",
                parse_mode="Markdown",
            )
            return

        tx_hash = await send_inj(wallet.encrypted_private_key, dest_address, amount)
        await update.message.reply_text(
            f"Sent `{amount} INJ` to `{dest_address}`\nTx: `{tx_hash}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"Withdrawal failed: {e}")


async def handle_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles tip messages in groups: @bot tip @username amount INJ"""
    message = update.message
    if not message or not message.text:
        return

    bot_username = context.bot.username
    if f"@{bot_username}" not in message.text:
        return

    parsed = parse_tip_command(message.text)
    if not parsed:
        await message.reply_text(
            f"Usage: @{bot_username} tip @username 0.1 INJ"
        )
        return

    target_username, amount = parsed
    sender = update.effective_user

    async with get_session() as session:
        # Refresh sender username in case it changed
        await repository.update_username(session, sender.id, sender.username)

        sender_wallet = await repository.get_wallet_by_user_id(session, sender.id)
        if not sender_wallet:
            await message.reply_text(
                f"@{sender.username}, you don't have a wallet yet. DM me /start to create one."
            )
            return

        receiver_wallet = await repository.get_wallet_by_username(session, target_username)
        if not receiver_wallet:
            await message.reply_text(
                f"@{target_username} doesn't have a wallet yet. They need to DM me /start."
            )
            return

        if receiver_wallet.user_id == sender.id:
            await message.reply_text("You can't tip yourself.")
            return

        try:
            balance = await get_balance(sender_wallet.address)
            if balance < amount + MIN_GAS_RESERVE:
                await message.reply_text(
                    f"@{sender.username}, insufficient balance. "
                    f"You have `{balance:.6f} INJ` (need {amount} + {MIN_GAS_RESERVE} for gas).",
                    parse_mode="Markdown",
                )
                return

            tx_hash = await send_inj(
                sender_wallet.encrypted_private_key,
                receiver_wallet.address,
                amount,
            )

            await repository.save_transaction(
                session,
                tx_hash=tx_hash,
                sender_id=sender.id,
                receiver_id=receiver_wallet.user_id,
                amount=str(amount),
                chat_id=message.chat_id,
            )

            await message.reply_text(
                f"Sent `{amount} INJ` from @{sender.username} to @{target_username}!\nTx: `{tx_hash}`",
                parse_mode="Markdown",
            )

        except Exception as e:
            await message.reply_text(f"Tip failed: {e}")
