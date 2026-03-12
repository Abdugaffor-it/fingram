import os
import sys
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BASE_DIR = Path(__file__).resolve().parent


def load_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


load_env()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", "")
BOT_NAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")

WELCOME_TEXT = (
    "Добро пожаловать в MoneyManagement.\n\n"
    "Что можно делать:\n"
    "1. Вести дневник доходов и расходов.\n"
    "2. Смотреть аналитику и советы по улучшению финансов.\n"
    "3. Использовать Web App прямо в Telegram.\n\n"
    "Команды:\n"
    "/start — приветствие\n"
    "/help — помощь\n"
    "/open — открыть Web App\n"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_TEXT, reply_markup=webapp_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Если вы впервые здесь, нажмите кнопку Web App и авторизуйтесь.\n"
        "Добавляйте доходы/расходы, следите за аналитикой и целями.\n",
        reply_markup=webapp_keyboard(),
    )


async def open_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Открываю Web App:", reply_markup=webapp_keyboard())


def webapp_keyboard() -> InlineKeyboardMarkup:
    if WEBAPP_URL:
        button = InlineKeyboardButton("Открыть MoneyManagement", web_app=WebAppInfo(url=WEBAPP_URL))
        return InlineKeyboardMarkup([[button]])
    if BOT_NAME:
        link = f"https://t.me/{BOT_NAME}?startapp=main"
        button = InlineKeyboardButton("Открыть MoneyManagement", url=link)
        return InlineKeyboardMarkup([[button]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("Нет настроенного URL", callback_data="noop")]])


def main() -> None:
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set. Add it to .env", file=sys.stderr)
        sys.exit(1)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("open", open_webapp))
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
