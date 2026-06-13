import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from db.database import init_db
from bot.handlers import (
    cmd_start, cmd_balance, cmd_wallet, cmd_withdraw,
    cmd_history, cmd_leaderboard, handle_tip, handle_callback,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def post_init(application: Application) -> None:
    await init_db()
    await application.bot.set_my_commands([
        BotCommand("start", "Create your Injective wallet"),
        BotCommand("balance", "Check your INJ balance"),
        BotCommand("wallet", "Show your wallet address"),
        BotCommand("history", "View your tip history"),
        BotCommand("leaderboard", "Top tippers in this group"),
        BotCommand("withdraw", "Withdraw INJ to an external address"),
    ])


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var not set")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("withdraw", cmd_withdraw))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tip))

    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
