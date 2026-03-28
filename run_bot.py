import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data.db"


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
ADMIN_USER_ID = str(os.environ.get("TELEGRAM_ADMIN_USER_ID", "")).strip()

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
    "/myid — показать ваш Telegram ID\n"
    "/admin — админ-панель\n"
    "/broadcast текст — рассылка по пользователям бота\n"
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_bot_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id TEXT UNIQUE NOT NULL,
            chat_id TEXT NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_blocked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_interaction_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_bot_user(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bot_users (
            telegram_user_id, chat_id, username, first_name, last_name,
            is_blocked, created_at, last_interaction_at
        )
        VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            chat_id = excluded.chat_id,
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            is_blocked = 0,
            last_interaction_at = excluded.last_interaction_at
        """
        ,
        (
            str(user.id),
            str(chat.id),
            user.username,
            user.first_name,
            user.last_name,
            now_iso(),
            now_iso(),
        ),
    )
    conn.commit()
    conn.close()


def mark_bot_user_blocked(telegram_user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE bot_users SET is_blocked = 1 WHERE telegram_user_id = ?", (telegram_user_id,))
    conn.commit()
    conn.close()


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and ADMIN_USER_ID and str(user.id) == ADMIN_USER_ID)


def webapp_keyboard() -> InlineKeyboardMarkup:
    if WEBAPP_URL:
        button = InlineKeyboardButton("Открыть MoneyManagement", web_app=WebAppInfo(url=WEBAPP_URL))
        return InlineKeyboardMarkup([[button]])
    if BOT_NAME:
        link = f"https://t.me/{BOT_NAME}?startapp=main"
        button = InlineKeyboardButton("Открыть MoneyManagement", url=link)
        return InlineKeyboardMarkup([[button]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("Нет настроенного URL", callback_data="noop")]])


def admin_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Обновить статистику", callback_data="admin:refresh")],
        [InlineKeyboardButton("Регистрации 7/30", callback_data="admin:registrations")],
        [InlineKeyboardButton("Рост пользователей", callback_data="admin:growth")],
        [InlineKeyboardButton("Рассылка", callback_data="admin:broadcast_prompt")],
    ]
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton("Открыть Web App", web_app=WebAppInfo(url=WEBAPP_URL))])
    elif BOT_NAME:
        rows.append([InlineKeyboardButton("Открыть Web App", url=f"https://t.me/{BOT_NAME}?startapp=main")])
    return InlineKeyboardMarkup(rows)


def secondary_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Назад в админ-панель", callback_data="admin:home")]])


def get_admin_stats():
    conn = get_db()
    cur = conn.cursor()
    active_since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cur.execute("SELECT COUNT(*) AS total FROM users")
    total_users = int(cur.fetchone()["total"] or 0)
    cur.execute(
        """
        SELECT COUNT(*) AS total
        FROM users
        WHERE last_seen_at IS NOT NULL AND last_seen_at >= ?
        """,
        (active_since,),
    )
    active_users = int(cur.fetchone()["total"] or 0)
    cur.execute("SELECT COUNT(*) AS total FROM bot_users WHERE is_blocked = 0")
    bot_subscribers = int(cur.fetchone()["total"] or 0)
    cur.execute(
        """
        SELECT id, display_name, email, telegram_user_id, last_seen_at
        FROM users
        ORDER BY COALESCE(last_seen_at, created_at) DESC
        LIMIT 5
        """
    )
    latest_users = cur.fetchall()
    conn.close()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "bot_subscribers": bot_subscribers,
        "latest_users": latest_users,
    }


def get_registration_stats():
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    since_7 = (now - timedelta(days=7)).isoformat()
    since_30 = (now - timedelta(days=30)).isoformat()
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE created_at >= ?", (since_7,))
    registered_7 = int(cur.fetchone()["total"] or 0)
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE created_at >= ?", (since_30,))
    registered_30 = int(cur.fetchone()["total"] or 0)
    cur.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
        FROM users
        WHERE created_at >= ?
        GROUP BY day
        ORDER BY day DESC
        LIMIT 7
        """,
        (since_7,),
    )
    recent_days = list(reversed(cur.fetchall()))
    conn.close()
    return {
        "registered_7": registered_7,
        "registered_30": registered_30,
        "recent_days": recent_days,
    }


def get_growth_stats(days=14):
    conn = get_db()
    cur = conn.cursor()
    start_day = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE substr(created_at, 1, 10) < ?", (start_day.isoformat(),))
    base_total = int(cur.fetchone()["total"] or 0)
    cur.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
        FROM users
        WHERE substr(created_at, 1, 10) >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (start_day.isoformat(),),
    )
    rows = {row["day"]: int(row["total"] or 0) for row in cur.fetchall()}
    conn.close()

    result = []
    running_total = base_total
    for offset in range(days):
        day = (start_day + timedelta(days=offset)).isoformat()
        daily = rows.get(day, 0)
        running_total += daily
        result.append({"day": day, "daily": daily, "total": running_total})
    return result


def render_bar(value: int, max_value: int, width=12) -> str:
    if max_value <= 0:
        return ""
    filled = max(1, round((value / max_value) * width)) if value > 0 else 0
    return "#" * filled


def render_admin_text():
    stats = get_admin_stats()
    lines = [
        "Админ-панель MoneyManagement",
        "",
        f"Всего пользователей: {stats['total_users']}",
        f"Активных за 7 дней: {stats['active_users']}",
        f"Подписчиков бота: {stats['bot_subscribers']}",
        "",
        "Последние активности:",
    ]
    if not stats["latest_users"]:
        lines.append("Нет данных.")
    else:
        for row in stats["latest_users"]:
            name = row["display_name"] or row["email"] or "Без имени"
            last_seen = row["last_seen_at"] or "еще не заходил"
            if row["telegram_user_id"]:
                identity = f"tg:{row['telegram_user_id']}"
            elif row["email"]:
                identity = row["email"]
            else:
                identity = f"id:{row['id']}"
            lines.append(f"- {name} ({identity}) | {last_seen}")
    return "\n".join(lines)


def render_registrations_text():
    stats = get_registration_stats()
    lines = [
        "Регистрации пользователей",
        "",
        f"За 7 дней: {stats['registered_7']}",
        f"За 30 дней: {stats['registered_30']}",
        "",
        "Последние 7 дней:",
    ]
    if not stats["recent_days"]:
        lines.append("Нет регистраций.")
    else:
        max_daily = max(int(row["total"] or 0) for row in stats["recent_days"])
        for row in stats["recent_days"]:
            day = row["day"]
            total = int(row["total"] or 0)
            lines.append(f"{day}: {total} {render_bar(total, max_daily)}")
    return "\n".join(lines)


def render_growth_text():
    growth = get_growth_stats()
    if not growth:
        return "Рост пользователей\n\nНет данных."
    max_daily = max(item["daily"] for item in growth) or 1
    lines = [
        "Рост пользователей за 14 дней",
        "",
        "Дата | Новые | Всего",
    ]
    for item in growth:
        day = item["day"][5:]
        daily = item["daily"]
        total = item["total"]
        lines.append(f"{day} | {daily:>3} {render_bar(daily, max_daily, 10):<10} | {total}")
    return "\n".join(lines)


async def send_admin_panel(target_message, update: Update):
    if not is_admin(update):
        await target_message.reply_text("У вас нет доступа к этой команде.")
        return
    await target_message.reply_text(render_admin_text(), reply_markup=admin_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    extra = ""
    if is_admin(update):
        extra = "\nУ вас есть доступ к /admin."
    await update.message.reply_text(WELCOME_TEXT + extra, reply_markup=webapp_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    await update.message.reply_text(
        "Если вы впервые здесь, нажмите кнопку Web App и авторизуйтесь.\n"
        "Добавляйте доходы и расходы, следите за аналитикой и целями.\n",
        reply_markup=webapp_keyboard(),
    )


async def open_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    await update.message.reply_text("Открываю Web App:", reply_markup=webapp_keyboard())


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    user = update.effective_user
    if not user:
        return
    await update.message.reply_text(f"Ваш Telegram user id: {user.id}")


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    context.user_data["awaiting_broadcast"] = False
    await send_admin_panel(update.message, update)


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    if not is_admin(update):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        context.user_data["awaiting_broadcast"] = True
        await update.message.reply_text(
            "Пришлите следующим сообщением текст рассылки.\n"
            "Для отмены используйте /admin."
        )
        return
    await run_broadcast(update, context, text)


async def run_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT telegram_user_id, chat_id
        FROM bot_users
        WHERE is_blocked = 0
        ORDER BY id ASC
        """
    )
    recipients = cur.fetchall()
    conn.close()

    sent = 0
    blocked = 0
    failed = 0
    for row in recipients:
        try:
            await context.bot.send_message(chat_id=row["chat_id"], text=text)
            sent += 1
        except Forbidden:
            blocked += 1
            mark_bot_user_blocked(str(row["telegram_user_id"]))
        except TelegramError:
            failed += 1

    context.user_data["awaiting_broadcast"] = False
    await update.message.reply_text(
        "Рассылка завершена.\n"
        f"Отправлено: {sent}\n"
        f"Заблокировали бота: {blocked}\n"
        f"Ошибки отправки: {failed}"
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if not is_admin(update):
        await query.edit_message_text("Доступ запрещен.")
        return

    if query.data in {"admin:home", "admin:refresh"}:
        context.user_data["awaiting_broadcast"] = False
        await query.edit_message_text(render_admin_text(), reply_markup=admin_keyboard())
        return
    if query.data == "admin:registrations":
        await query.edit_message_text(render_registrations_text(), reply_markup=secondary_admin_keyboard())
        return
    if query.data == "admin:growth":
        await query.edit_message_text(render_growth_text(), reply_markup=secondary_admin_keyboard())
        return
    if query.data == "admin:broadcast_prompt":
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text(
            "Режим рассылки включен.\n"
            "Отправьте следующим сообщением текст, который нужно разослать всем пользователям бота.",
            reply_markup=secondary_admin_keyboard(),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_bot_user(update)
    if not is_admin(update):
        return
    if context.user_data.get("awaiting_broadcast"):
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("Текст рассылки пустой. Отправьте обычное сообщение.")
            return
        await run_broadcast(update, context, text)


def main() -> None:
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set. Add it to .env", file=sys.stderr)
        sys.exit(1)
    init_bot_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("open", open_webapp))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
