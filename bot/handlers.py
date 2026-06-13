from decimal import Decimal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

from db.database import get_session
from db import repository
from wallet.injective_wallet import create_wallet, get_balance, send_inj, send_token, send_nft, MIN_GAS_RESERVE
from wallet.crypto import decrypt_private_key
from wallet.tokens import resolve_token, resolve_nft, TOKENS, NFTS
from utils.parsing import parse_tip_command


def _h(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Balance", callback_data="balance"),
            InlineKeyboardButton("👛 Wallet", callback_data="wallet"),
        ],
        [
            InlineKeyboardButton("📜 History", callback_data="history"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton("📤 Withdraw", callback_data="withdraw_help"),
        ],
        [
            InlineKeyboardButton("🔑 Export Key", callback_data="export_key"),
        ],
    ])


async def _send_balance(user_id: int, message: Message) -> None:
    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user_id)
    if not wallet:
        await message.reply_text("No wallet found. Use /start to create one.")
        return
    try:
        balance = await get_balance(wallet.address)
        await message.reply_text(
            f"💰 <b>Balance</b>\n\n<code>{balance:.6f} INJ</code>\n\nAddress:\n<code>{_h(wallet.address)}</code>",
            parse_mode="HTML",
            reply_markup=_main_menu(),
        )
    except Exception as e:
        await message.reply_text(f"Could not fetch balance: {_h(str(e))}", parse_mode="HTML")


async def _send_wallet(user_id: int, message: Message) -> None:
    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user_id)
    if not wallet:
        await message.reply_text("No wallet found. Use /start to create one.")
        return
    await message.reply_text(
        f"👛 <b>Your Wallet</b>\n\n<code>{_h(wallet.address)}</code>",
        parse_mode="HTML",
        reply_markup=_main_menu(),
    )


async def _send_history(user_id: int, message: Message) -> None:
    async with get_session() as session:
        wallet = await repository.get_wallet_by_user_id(session, user_id)
        if not wallet:
            await message.reply_text("No wallet found. Use /start to create one.")
            return
        sent, received = await repository.get_user_history(session, user_id)
        user_ids = list({t.sender_user_id for t in received} | {t.receiver_user_id for t in sent})
        wallets = await repository.get_wallet_by_user_ids(session, user_ids)

    lines = ["📜 <b>Tip History</b>\n"]
    if sent:
        lines.append("<b>Sent:</b>")
        for t in sent:
            recv = wallets.get(t.receiver_user_id)
            name = f"@{_h(recv.username)}" if recv and recv.username else f"user {t.receiver_user_id}"
            lines.append(f"  ➡️ {name} — <code>{Decimal(t.amount):.3f} INJ</code>")
    else:
        lines.append("<b>Sent:</b> none yet")
    lines.append("")
    if received:
        lines.append("<b>Received:</b>")
        for t in received:
            sndr = wallets.get(t.sender_user_id)
            name = f"@{_h(sndr.username)}" if sndr and sndr.username else f"user {t.sender_user_id}"
            lines.append(f"  ⬅️ {name} — <code>{Decimal(t.amount):.3f} INJ</code>")
    else:
        lines.append("<b>Received:</b> none yet")

    await message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=_main_menu())


async def _send_leaderboard(chat_id: int, chat_title: str, message: Message) -> None:
    async with get_session() as session:
        rows = await repository.get_group_leaderboard(session, chat_id)
        wallets = await repository.get_wallet_by_user_ids(session, [r[0] for r in rows])

    if not rows:
        await message.reply_text("No tips have been sent in this group yet.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 <b>Top Tippers — {_h(chat_title)}</b>\n"]
    for i, (uid, total) in enumerate(rows):
        w = wallets.get(uid)
        name = f"@{_h(w.username)}" if w and w.username else f"user {uid}"
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {name} — <code>{total:.4f} INJ</code>")

    await message.reply_text("\n".join(lines), parse_mode="HTML")


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    async with get_session() as session:
        existing = await repository.get_wallet_by_user_id(session, user.id)
        if existing:
            await update.message.reply_text(
                f"👋 Welcome back, <b>{_h(user.first_name)}</b>!\n\nAddress:\n<code>{_h(existing.address)}</code>",
                parse_mode="HTML",
                reply_markup=_main_menu(),
            )
            return

        address, encrypted_key, private_key_hex, mnemonic = create_wallet()
        await repository.create_wallet(
            session, user_id=user.id, username=user.username,
            address=address, encrypted_private_key=encrypted_key,
        )

    await update.message.reply_text(
        f"✅ <b>Wallet Created!</b>\n\n"
        f"<b>Address:</b>\n<code>{_h(address)}</code>\n\n"
        f"<b>Private Key:</b>\n<code>{_h(private_key_hex)}</code>\n\n"
        f"<b>Secret Phrase (12 words):</b>\n<code>{_h(mnemonic)}</code>\n\n"
        f"⚠️ <b>Save your secret phrase and private key — they will NOT be shown again.</b>\n\n"
        f"Fund your wallet with INJ and start tipping!",
        parse_mode="HTML",
        reply_markup=_main_menu(),
    )


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_balance(update.effective_user.id, update.message)


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_wallet(update.effective_user.id, update.message)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_history(update.effective_user.id, update.message)


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("Use /leaderboard in a group to see the top tippers there.")
        return
    await _send_leaderboard(chat.id, chat.title or "this group", update.message)


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args

    if len(args) != 2:
        await update.message.reply_text(
            "📤 <b>Withdraw</b>\n\nUsage:\n<code>/withdraw inj1address amount</code>",
            parse_mode="HTML",
        )
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
                f"Insufficient balance. You have <code>{balance:.6f} INJ</code> "
                f"(need {amount} + {MIN_GAS_RESERVE} for gas).",
                parse_mode="HTML",
            )
            return

        tx_hash = await send_inj(wallet.encrypted_private_key, dest_address, amount)
        await update.message.reply_text(
            f"✅ Sent <code>{amount} INJ</code> to\n<code>{_h(dest_address)}</code>\n\nTx: <code>{_h(tx_hash)}</code>",
            parse_mode="HTML",
            reply_markup=_main_menu(),
        )
    except Exception as e:
        await update.message.reply_text(f"Withdrawal failed: {_h(str(e))}", parse_mode="HTML")


# ── Group tip handler ─────────────────────────────────────────────────────────

async def handle_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    bot_username = context.bot.username
    if f"@{bot_username}" not in message.text:
        return

    parsed = parse_tip_command(message.text)
    if not parsed:
        await message.reply_text(f"Usage: @{bot_username} tip @username 0.1 INJ")
        return

    target_username, amount, symbol = parsed
    sender = update.effective_user

    async with get_session() as session:
        await repository.update_username(session, sender.id, sender.username)

        sender_wallet = await repository.get_wallet_by_user_id(session, sender.id)
        if not sender_wallet:
            await message.reply_text(
                f"@{_h(sender.username)}, you don't have a wallet yet. DM me /start to create one.",
                parse_mode="HTML",
            )
            return

        receiver_wallet = await repository.get_wallet_by_username(session, target_username)
        if not receiver_wallet:
            await message.reply_text(
                f"@{_h(target_username)} doesn't have a wallet yet. They need to DM me /start.",
                parse_mode="HTML",
            )
            return

        if receiver_wallet.user_id == sender.id:
            await message.reply_text("You can't tip yourself.")
            return

        nft_info = resolve_nft(symbol)
        token_info = resolve_token(symbol)

        if not nft_info and not token_info:
            supported = ", ".join(list(TOKENS.keys()) + list(NFTS.keys()))
            await message.reply_text(
                f"Unknown token or NFT: <code>{_h(symbol)}</code>.\nSupported: <code>{_h(supported)}</code>",
                parse_mode="HTML",
            )
            return

        try:
            sender_name = sender.username or sender.first_name

            if nft_info:
                # NFT tip
                try:
                    token_id, tx_hash = await send_nft(
                        sender_wallet.encrypted_private_key,
                        receiver_wallet.address,
                        nft_info["contract"],
                    )
                except RuntimeError as e:
                    await message.reply_text(f"NFT tip failed: {_h(str(e))}", parse_mode="HTML")
                    return

                await repository.save_transaction(
                    session, tx_hash=tx_hash, sender_id=sender.id,
                    receiver_id=receiver_wallet.user_id, amount=token_id,
                    chat_id=message.chat_id,
                )
                tip_text = f"<code>#{_h(token_id)}</code> {_h(nft_info['display'])}"
                dm_text = f"🎉 <b>You received an NFT!</b>\n\n<b>@{_h(sender_name)}</b> sent you {tip_text}\n\nTx: <code>{_h(tx_hash)}</code>"
            else:
                # Fungible token tip
                balance = await get_balance(sender_wallet.address)
                if balance < MIN_GAS_RESERVE:
                    await message.reply_text(
                        f"@{_h(sender.username)}, insufficient INJ for gas. "
                        f"You need at least <code>{MIN_GAS_RESERVE} INJ</code>.",
                        parse_mode="HTML",
                    )
                    return

                tx_hash = await send_token(
                    sender_wallet.encrypted_private_key,
                    receiver_wallet.address,
                    amount,
                    token_info,
                )

                await repository.save_transaction(
                    session, tx_hash=tx_hash, sender_id=sender.id,
                    receiver_id=receiver_wallet.user_id,
                    amount=f"{amount} {token_info['display']}",
                    chat_id=message.chat_id,
                )
                tip_text = f"<code>{amount} {_h(token_info['display'])}</code>"
                dm_text = f"🎉 <b>You received a tip!</b>\n\n<b>@{_h(sender_name)}</b> tipped you {tip_text}\n\nTx: <code>{_h(tx_hash)}</code>"

            await message.reply_text(
                f"✅ <b>Tip sent!</b>\n\n"
                f"<b>@{_h(sender_name)}</b> ➡️ <b>@{_h(target_username)}</b>\n"
                f"Amount: {tip_text}\n"
                f"Tx: <code>{_h(tx_hash)}</code>",
                parse_mode="HTML",
            )

            try:
                await context.bot.send_message(
                    chat_id=receiver_wallet.user_id,
                    text=dm_text,
                    parse_mode="HTML",
                    reply_markup=_main_menu(),
                )
            except Exception:
                pass

        except Exception as e:
            await message.reply_text(f"Tip failed: {_h(str(e))}", parse_mode="HTML")


# ── Inline button callbacks ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    msg = query.message
    data = query.data

    if data == "balance":
        await _send_balance(user.id, msg)
    elif data == "wallet":
        await _send_wallet(user.id, msg)
    elif data == "history":
        await _send_history(user.id, msg)
    elif data == "leaderboard":
        chat = update.effective_chat
        if chat.type == "private":
            await msg.reply_text("Open a group and use /leaderboard there.")
        else:
            await _send_leaderboard(chat.id, chat.title or "this group", msg)
    elif data == "export_key":
        if update.effective_chat.type != "private":
            await query.answer("For security, use this in DM with the bot.", show_alert=True)
            return
        async with get_session() as session:
            wallet = await repository.get_wallet_by_user_id(session, user.id)
        if not wallet:
            await msg.reply_text("No wallet found. Use /start to create one.")
            return
        try:
            private_key_hex = decrypt_private_key(wallet.encrypted_private_key)
        except Exception:
            await msg.reply_text("Failed to decrypt private key.")
            return
        await msg.reply_text(
            f"🔑 <b>Your Private Key</b>\n\n"
            f"<code>{_h(private_key_hex)}</code>\n\n"
            f"⚠️ <b>Never share this with anyone.</b>",
            parse_mode="HTML",
            reply_markup=_main_menu(),
        )
    elif data == "withdraw_help":
        await msg.reply_text(
            "📤 <b>Withdraw</b>\n\nSend me:\n<code>/withdraw inj1youraddress 0.5</code>",
            parse_mode="HTML",
        )
