import os
import sqlite3
import json
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl
from flask import Flask, jsonify, request, session, send_from_directory, render_template, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("APP_SECRET", "dev-secret-change-me")
ALLOWED_CURRENCIES = {"TJS", "RUB", "USD", "KZT", "UZS"}
SITE_NAME = "Fin-gram"
SUPPORTED_LANGS = ("ru", "en")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            display_name TEXT,
            telegram_user_id TEXT UNIQUE,
            preferred_currency TEXT,
            monthly_income_target REAL,
            monthly_savings_goal REAL,
            emergency_fund_target_months REAL,
            last_seen_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            category TEXT NOT NULL,
            note TEXT,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute("PRAGMA table_info(users)")
    columns = {row["name"] for row in cur.fetchall()}
    if "preferred_currency" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN preferred_currency TEXT")
    if "monthly_income_target" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN monthly_income_target REAL")
    if "monthly_savings_goal" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN monthly_savings_goal REAL")
    if "emergency_fund_target_months" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN emergency_fund_target_months REAL")
    if "last_seen_at" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")
    cur.execute("UPDATE users SET preferred_currency = COALESCE(preferred_currency, 'USD')")
    cur.execute(
        "UPDATE users SET emergency_fund_target_months = COALESCE(emergency_fund_target_months, 3)"
    )
    conn.commit()
    conn.close()

init_db()


LANDING_CONTENT = {
    "ru": {
        "lang_name": "Русский",
        "hero_title": "Fin-gram помогает держать деньги под контролем каждый день.",
        "hero_subtitle": "Учет доходов и расходов, аналитика капитала и Telegram Web App в одном строгом интерфейсе.",
        "cta_primary": "Открыть Web App",
        "cta_secondary": "Открыть в Telegram",
        "badge": "Финансовый дневник в Telegram",
        "section_title": "Почему выбирают Fin-gram",
        "features": [
            {
                "title": "Быстрые записи",
                "text": "Добавляйте доходы и расходы за несколько секунд с понятными категориями и единой валютой профиля.",
            },
            {
                "title": "Глубокая аналитика",
                "text": "Смотрите структуру расходов, соотношение доходов и накоплений, тренды и ключевые метрики.",
            },
            {
                "title": "Telegram внутри процесса",
                "text": "Открывайте приложение прямо из Telegram и держите финансовый журнал под рукой на телефоне.",
            },
        ],
        "steps_title": "Как это работает",
        "steps": [
            "Авторизуйтесь через email или Telegram Web App.",
            "Фиксируйте доходы и расходы по датам и категориям.",
            "Следите за динамикой, концентрацией расходов и советами по улучшению финансов.",
        ],
        "use_cases_title": "Кому подходит",
        "use_cases": [
            "Личный учет расходов и доходов.",
            "Контроль семейного бюджета.",
            "Финансовая дисциплина для фрилансеров и предпринимателей.",
        ],
        "preview_title": "Что вы получаете внутри",
        "preview_points": [
            "Дашборд с доходом, расходом и итогом месяца.",
            "Аналитика по категориям, периодам и источникам дохода.",
            "Финансовые советы на основе ваших реальных данных.",
        ],
        "faq_teaser_title": "Частые вопросы",
        "faq_teaser_text": "Подготовили ответы о безопасности, Telegram Web App и финансовой аналитике.",
        "faq_cta": "Открыть FAQ",
        "blog_title": "Полезные материалы",
        "blog_teaser": "Статьи для тех, кто хочет лучше управлять бюджетом и личными финансами.",
    },
    "en": {
        "lang_name": "English",
        "hero_title": "Fin-gram keeps your money under control every day.",
        "hero_subtitle": "Track income and expenses, monitor capital, and use a Telegram Web App in one premium workflow.",
        "cta_primary": "Open Web App",
        "cta_secondary": "Open in Telegram",
        "badge": "Finance journal inside Telegram",
        "section_title": "Why people choose Fin-gram",
        "features": [
            {
                "title": "Fast entry flow",
                "text": "Capture income and expenses in seconds with clear categories and one default profile currency.",
            },
            {
                "title": "Deeper analytics",
                "text": "Understand spending structure, savings ratio, cash flow trends, and the metrics that matter.",
            },
            {
                "title": "Telegram-native workflow",
                "text": "Launch the app right from Telegram and keep your finance journal one tap away on mobile.",
            },
        ],
        "steps_title": "How it works",
        "steps": [
            "Sign in with email or Telegram Web App.",
            "Record income and expenses by date and category.",
            "Use analytics, concentration metrics, and tailored financial tips.",
        ],
        "use_cases_title": "Who it is for",
        "use_cases": [
            "Personal expense and income tracking.",
            "Household budget control.",
            "Financial discipline for freelancers and founders.",
        ],
        "preview_title": "What you get inside",
        "preview_points": [
            "A dashboard with monthly income, expense, and net result.",
            "Analytics by category, period, and income source.",
            "Practical financial advice based on your own data.",
        ],
        "faq_teaser_title": "Frequently asked questions",
        "faq_teaser_text": "Answers about security, Telegram Web App usage, and finance analytics.",
        "faq_cta": "Open FAQ",
        "blog_title": "Guides and insights",
        "blog_teaser": "Content for people who want stronger control over budgeting and personal finance.",
    },
}

FAQ_CONTENT = {
    "ru": [
        {
            "q": "Что такое Fin-gram?",
            "a": "Fin-gram — это веб-приложение и Telegram Web App для учета доходов, расходов и просмотра финансовой аналитики.",
        },
        {
            "q": "Можно ли пользоваться через Telegram?",
            "a": "Да. Вы можете открыть Fin-gram прямо из Telegram-бота и работать с приложением как с Telegram Web App.",
        },
        {
            "q": "Подходит ли Fin-gram для личного бюджета?",
            "a": "Да. Приложение рассчитано на личные финансы, семейный бюджет, контроль расходов и накоплений.",
        },
        {
            "q": "Нужна ли регистрация?",
            "a": "Да. Перед использованием кабинета пользователь авторизуется через email или Telegram, после чего получает доступ к личным данным и аналитике.",
        },
    ],
    "en": [
        {
            "q": "What is Fin-gram?",
            "a": "Fin-gram is a web app and Telegram Web App for tracking income, expenses, and personal finance analytics.",
        },
        {
            "q": "Can I use it inside Telegram?",
            "a": "Yes. You can launch Fin-gram from the Telegram bot and use it directly as a Telegram Web App.",
        },
        {
            "q": "Is Fin-gram built for personal budgeting?",
            "a": "Yes. It is designed for personal finance tracking, household budgeting, and spending control.",
        },
        {
            "q": "Do I need to sign in first?",
            "a": "Yes. Users authenticate with email or Telegram before they can use the private app and analytics.",
        },
    ],
}

BLOG_POSTS = {
    "expense-income-journal": {
        "ru": {
            "title": "Как вести учет доходов и расходов без перегруза",
            "description": "Практический подход к учету доходов и расходов: как фиксировать операции, выбирать категории и не потерять дисциплину.",
            "intro": "Сильный контроль над личными финансами начинается не со сложных таблиц, а с регулярной фиксации движения денег. Если учет неудобный, привычка не закрепится.",
            "sections": [
                {
                    "title": "Начинайте с простого ритма",
                    "body": "Вам не нужен сложный финансовый комбайн. Достаточно ежедневно записывать каждую операцию, выбирать понятную категорию и в конце недели смотреть на общую картину.",
                },
                {
                    "title": "Категории должны быть понятными",
                    "body": "Категории расходов и доходов должны помогать принимать решения. Если категория не помогает понять, где уходит бюджет, ее нужно упростить или объединить.",
                },
                {
                    "title": "Смотрите не только сумму, но и структуру",
                    "body": "Важно не только сколько вы тратите, но и на что именно. Структура расходов по дням и категориям позволяет заметить повторяющиеся паттерны и убрать лишние траты.",
                },
            ],
        },
        "en": {
            "title": "How to keep an income and expense journal without friction",
            "description": "A practical guide to logging income and expenses, choosing categories, and building a sustainable money tracking habit.",
            "intro": "Good personal finance control starts with consistency, not complexity. If tracking feels heavy, the habit breaks quickly.",
            "sections": [
                {
                    "title": "Start with a simple daily rhythm",
                    "body": "You do not need a massive spreadsheet. A daily logging habit, clear categories, and a weekly review already create strong financial awareness.",
                },
                {
                    "title": "Use categories that help decisions",
                    "body": "Categories should reveal where your budget is going. If a category does not guide action, simplify it or merge it into a cleaner structure.",
                },
                {
                    "title": "Track patterns, not just totals",
                    "body": "Total spending matters, but spending structure matters more. Category and date trends help you spot recurring leaks and make better financial decisions.",
                },
            ],
        },
    },
    "budget-control": {
        "ru": {
            "title": "Как контролировать личный бюджет и не срываться",
            "description": "Стратегия контроля личного бюджета: как отслеживать деньги, выставлять ориентиры и сохранять финансовую дисциплину.",
            "intro": "Контроль бюджета — это не жесткие ограничения, а ясность. Когда вы видите доходы, расходы и чистый результат, становится проще принимать спокойные решения.",
            "sections": [
                {
                    "title": "Определите базовые ориентиры",
                    "body": "Установите ориентир по доходу, по расходам и по накоплению. Даже простые цели помогают понять, движетесь ли вы в нужную сторону в течение месяца.",
                },
                {
                    "title": "Проверяйте бюджет регулярно",
                    "body": "Раз в неделю сверяйте фактические расходы с ожиданиями. Это снижает риск, что деньги уйдут незаметно в одной крупной категории.",
                },
                {
                    "title": "Используйте аналитику как систему обратной связи",
                    "body": "Графики и сравнение периодов нужны не для красоты, а для действий: сократить лишнее, стабилизировать кэшфлоу и улучшить накопления.",
                },
            ],
        },
        "en": {
            "title": "How to control a personal budget without burning out",
            "description": "A practical budgeting strategy for tracking money, setting reference points, and staying consistent over time.",
            "intro": "Budget control is not about pressure. It is about visibility. Once you can clearly see income, expenses, and net result, better decisions become easier.",
            "sections": [
                {
                    "title": "Set a few reference points",
                    "body": "Define simple goals for income, spending, and savings. Even lightweight targets give you a frame for evaluating the month.",
                },
                {
                    "title": "Review the budget on a schedule",
                    "body": "A weekly check-in is often enough to catch overspending before it becomes a bigger problem.",
                },
                {
                    "title": "Use analytics as feedback",
                    "body": "Charts and comparisons are useful when they drive action: adjust category limits, stabilize cash flow, and improve savings behavior.",
                },
            ],
        },
    },
    "telegram-finance": {
        "ru": {
            "title": "Как использовать Telegram для управления личными финансами",
            "description": "Почему Telegram Web App удобен для учета расходов и доходов, и как встроить финансовую дисциплину в ежедневный мессенджер.",
            "intro": "Чем меньше трения между вами и учетом денег, тем выше шанс, что вы действительно будете вести записи. Поэтому Telegram может быть сильной точкой входа в личные финансы.",
            "sections": [
                {
                    "title": "Финансовый инструмент там, где вы уже бываете каждый день",
                    "body": "Когда учет доступен прямо в Telegram, не нужно переключаться между множеством сервисов. Это сокращает путь от расхода до записи.",
                },
                {
                    "title": "Telegram Web App подходит для мобильного сценария",
                    "body": "Мобильный интерфейс внутри мессенджера удобен для быстрых действий: добавить запись, проверить месяц, посмотреть категорию-лидер по расходам.",
                },
                {
                    "title": "Главное — не только удобство, но и системность",
                    "body": "Даже лучший интерфейс не заменит регулярность. Используйте Telegram как точку входа, а аналитику — как инструмент для корректировки финансового поведения.",
                },
            ],
        },
        "en": {
            "title": "How to use Telegram for personal finance management",
            "description": "Why a Telegram Web App can be effective for expense tracking, income logging, and keeping a stronger money habit.",
            "intro": "The lower the friction, the higher the chance that you will actually keep your finances updated. That is why Telegram can become a powerful entry point for personal finance tracking.",
            "sections": [
                {
                    "title": "Your finance tool lives where you already spend time",
                    "body": "If tracking is available inside Telegram, there is less switching cost and a shorter path from a transaction to a recorded entry.",
                },
                {
                    "title": "Telegram Web Apps fit mobile finance workflows",
                    "body": "The mobile-first flow is useful for fast actions: add a new entry, review the month, or check which category dominates spending.",
                },
                {
                    "title": "Convenience matters, but consistency matters more",
                    "body": "Telegram is the entry point. The real value comes from reviewing analytics and using them to improve your financial behavior over time.",
                },
            ],
        },
    },
    "family-budget": {
        "ru": {
            "title": "Как вести семейный бюджет без постоянных конфликтов",
            "description": "Практические принципы ведения семейного бюджета: общие правила, прозрачность расходов и понятная структура финансовых решений.",
            "intro": "Семейный бюджет ломается не только из-за нехватки денег, но и из-за отсутствия общей системы. Когда правила не проговорены, даже мелкие траты становятся источником напряжения.",
            "sections": [
                {
                    "title": "Договоритесь о базовой структуре",
                    "body": "Сначала разделите обязательные расходы, переменные траты и цели накопления. Это создаёт общую карту и убирает хаос из обсуждений.",
                },
                {
                    "title": "Фиксируйте расходы в одном месте",
                    "body": "Когда все операции попадают в единый журнал, разговор переходит от эмоций к фактам. Это помогает быстрее увидеть, где бюджет действительно проседает.",
                },
                {
                    "title": "Смотрите на тренды, а не на один день",
                    "body": "Один дорогой день ещё не означает финансовую проблему. Реальные выводы появляются, когда вы анализируете категории и динамику по неделям и месяцам.",
                },
            ],
        },
        "en": {
            "title": "How to manage a family budget without constant tension",
            "description": "A practical approach to family budgeting with shared rules, transparent spending, and calmer financial decisions.",
            "intro": "Family budgeting often breaks down because there is no shared system. Without clear rules, even small purchases can become a source of friction.",
            "sections": [
                {
                    "title": "Agree on a basic structure first",
                    "body": "Separate fixed costs, variable spending, and savings goals. That gives everyone a shared financial map.",
                },
                {
                    "title": "Track spending in one place",
                    "body": "When all expenses live in one journal, discussions move from emotion to evidence. That makes budgeting much easier to manage.",
                },
                {
                    "title": "Focus on trends, not one bad day",
                    "body": "One expensive day is not the whole story. Monthly and category trends reveal the real pressure points in a household budget.",
                },
            ],
        },
    },
    "savings-habits": {
        "ru": {
            "title": "Как выстроить привычку накоплений без жестких ограничений",
            "description": "Как превратить накопления в устойчивую привычку: ориентиры, автоматизация и контроль личных финансов без изматывающего режима.",
            "intro": "Накопления редко держатся только на силе воли. Система работает лучше, когда вы заранее понимаете цель, размер откладываемой суммы и видите прогресс.",
            "sections": [
                {
                    "title": "Сначала определите реалистичную сумму",
                    "body": "Лучше откладывать умеренную сумму регулярно, чем пытаться экономить слишком агрессивно и быстро потерять устойчивость.",
                },
                {
                    "title": "Свяжите накопления с ежемесячным обзором",
                    "body": "Когда вы видите доход, расход и чистый результат месяца, проще принять решение, сколько можно безопасно направить в резерв или цель.",
                },
                {
                    "title": "Используйте аналитику как мотиватор",
                    "body": "Графики и цели помогают видеть не только ограничения, но и прогресс. Это делает накопления психологически проще и понятнее.",
                },
            ],
        },
        "en": {
            "title": "How to build a savings habit without extreme restrictions",
            "description": "A practical guide to building sustainable savings through realistic targets, automation, and better financial visibility.",
            "intro": "Savings rarely survive on willpower alone. A stronger system starts with clear targets, reasonable amounts, and visible progress.",
            "sections": [
                {
                    "title": "Choose a realistic amount first",
                    "body": "A moderate monthly savings habit is stronger than an aggressive plan that quickly collapses under pressure.",
                },
                {
                    "title": "Connect savings to your monthly review",
                    "body": "When you can see income, expenses, and net result clearly, it becomes easier to decide how much money can safely move into savings.",
                },
                {
                    "title": "Use analytics as motivation",
                    "body": "Charts and goals help you see momentum, not only constraints. That makes saving feel more achievable over time.",
                },
            ],
        },
    },
}

ABOUT_CONTENT = {
    "ru": {
        "title": "О Fin-gram",
        "description": "Fin-gram — это продукт для учета расходов и доходов, который объединяет веб-приложение, Telegram Web App и финансовую аналитику.",
        "lead": "Fin-gram создан для людей, которым нужен современный и понятный способ контролировать деньги без сложных таблиц и перегруженных интерфейсов.",
        "cards": [
            {"title": "Продуктовая идея", "text": "Свести учёт, аналитику и Telegram в одну систему, где финансовая дисциплина не требует лишнего трения."},
            {"title": "Для кого", "text": "Для личного бюджета, семейных финансов, фриланса и повседневного контроля капитала."},
            {"title": "Подход", "text": "Меньше хаоса, больше ясности: понятные категории, быстрые записи, заметная аналитика и советы по данным."},
        ],
    },
    "en": {
        "title": "About Fin-gram",
        "description": "Fin-gram is a product for income and expense tracking that combines a web app, Telegram Web App, and financial analytics.",
        "lead": "Fin-gram is built for people who want a modern and clear way to control money without heavy spreadsheets or bloated finance tools.",
        "cards": [
            {"title": "Product vision", "text": "Bring tracking, analytics, and Telegram into one workflow with less friction and better financial clarity."},
            {"title": "Who it is for", "text": "Personal budgeting, household finance, freelance income tracking, and everyday money control."},
            {"title": "Approach", "text": "Less chaos, more visibility: clean categories, fast entry, strong analytics, and data-backed advice."},
        ],
    },
}

PRICING_CONTENT = {
    "ru": {
        "title": "Цены Fin-gram",
        "description": "Текущая версия Fin-gram доступна как продукт раннего этапа с фокусом на запуск, рост и обратную связь пользователей.",
        "lead": "Сейчас Fin-gram развивается как ранний продукт. Публичная pricing-страница нужна для SEO, позиционирования и будущих тарифов.",
        "plans": [
            {"name": "Starter", "price": "Скоро", "text": "Базовый учет доходов и расходов, Telegram Web App и основные отчеты."},
            {"name": "Pro", "price": "Скоро", "text": "Расширенная аналитика, цели, рекомендации и более глубокий финансовый контроль."},
            {"name": "Team / Family", "price": "Скоро", "text": "Совместные сценарии, семейный бюджет и расширенная структура финансовых ролей."},
        ],
    },
    "en": {
        "title": "Fin-gram Pricing",
        "description": "The current Fin-gram release is an early-stage product focused on launch, growth, and user feedback.",
        "lead": "Fin-gram is currently in an early product phase. This public pricing page supports SEO, positioning, and future plan rollout.",
        "plans": [
            {"name": "Starter", "price": "Coming soon", "text": "Core income and expense tracking, Telegram Web App access, and essential reporting."},
            {"name": "Pro", "price": "Coming soon", "text": "Advanced analytics, goals, recommendations, and deeper financial control."},
            {"name": "Team / Family", "price": "Coming soon", "text": "Shared workflows, household budgeting, and richer financial collaboration."},
        ],
    },
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today_iso():
    return datetime.now(timezone.utc).date().isoformat()


def normalize_entry_date(value):
    if not value:
        return today_iso()
    value = str(value).strip()
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return today_iso()


def month_range_utc(now):
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def month_start_end(year, month):
    start = datetime(year=year, month=month, day=1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year=year + 1, month=1, day=1, tzinfo=timezone.utc)
    else:
        end = datetime(year=year, month=month + 1, day=1, tzinfo=timezone.utc)
    return start, end


def get_user_currency(cur, user_id):
    cur.execute("SELECT preferred_currency FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        return "USD"
    currency = (row["preferred_currency"] or "USD").upper()
    return currency if currency in ALLOWED_CURRENCIES else "USD"


def require_auth():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


def touch_user_activity(user_id):
    if not user_id:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now_iso(), user_id))
    conn.commit()
    conn.close()


def verify_telegram_init_data(init_data: str, bot_token: str) -> bool:
    if not init_data or not bot_token:
        return False
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", "")
    if not received_hash:
        return False
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        return False
    auth_date = data.get("auth_date")
    if auth_date:
        try:
            auth_dt = datetime.fromtimestamp(int(auth_date), tz=timezone.utc)
            if (datetime.now(timezone.utc) - auth_dt).total_seconds() > 86400:
                return False
        except ValueError:
            return False
    return True


def get_site_url():
    explicit = (os.environ.get("SITE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    return request.url_root.rstrip("/")


def get_telegram_bot_link():
    username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip()
    if username:
        return f"https://t.me/{username}"
    return None


def get_telegram_webapp_link():
    configured = (os.environ.get("TELEGRAM_WEBAPP_URL") or "").strip()
    if configured:
        return configured
    username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip()
    if username:
        return f"https://t.me/{username}?startapp=main"
    return f"{get_site_url()}/app"


def build_hreflangs(path_suffix=""):
    site_url = get_site_url()
    normalized = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}" if path_suffix else ""
    return {
        "ru": f"{site_url}/ru{normalized}" if normalized else f"{site_url}/ru",
        "en": f"{site_url}/en{normalized}" if normalized else f"{site_url}/en",
        "x-default": f"{site_url}/ru{normalized}" if normalized else f"{site_url}/ru",
    }


def base_structured_data():
    site_url = get_site_url()
    return [
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": SITE_NAME,
            "url": site_url,
            "logo": f"{site_url}/static/og-fin-gram.svg",
        },
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": SITE_NAME,
            "url": site_url,
            "inLanguage": ["ru", "en"],
        },
    ]


def marketing_page_context(lang, page_title, description, canonical_url, path_suffix=""):
    lang_copy = LANDING_CONTENT[lang]
    site_url = get_site_url()
    return {
        "lang": lang,
        "site_name": SITE_NAME,
        "page_title": page_title,
        "description": description,
        "canonical_url": canonical_url,
        "site_url": site_url,
        "og_image": f"{site_url}/static/og-fin-gram.svg",
        "telegram_link": get_telegram_bot_link(),
        "webapp_link": get_telegram_webapp_link(),
        "hreflangs": build_hreflangs(path_suffix),
        "lang_switch_url": f"/{'en' if lang == 'ru' else 'ru'}{path_suffix}",
        "lang_switch_label": "English" if lang == "ru" else "Русский",
        "lang_name": lang_copy["lang_name"],
        "brand_badge": lang_copy["badge"],
    }


@app.after_request
def add_robot_headers(response):
    if request.path.startswith("/api/") or request.path == "/app":
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/")
def marketing_home():
    return landing("ru")


@app.route("/app")
def app_home():
    response = make_response(render_template("app.html"))
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/<lang>")
def landing(lang):
    if lang not in SUPPORTED_LANGS:
        abort(404)
    content = LANDING_CONTENT[lang]
    page_title = (
        "Fin-gram — учет расходов и доходов в Telegram"
        if lang == "ru"
        else "Fin-gram — Expense Tracker and Telegram Finance App"
    )
    description = (
        "Fin-gram помогает вести учет расходов и доходов, смотреть аналитику и управлять личными финансами через веб-приложение и Telegram."
        if lang == "ru"
        else "Fin-gram helps you track income and expenses, review analytics, and manage personal finances through a web app and Telegram."
    )
    context = marketing_page_context(lang, page_title, description, f"{get_site_url()}/{lang}")
    context.update(
        {
            "page_kind": "landing",
            "content": content,
            "posts": [
                {"slug": slug, "title": BLOG_POSTS[slug][lang]["title"], "description": BLOG_POSTS[slug][lang]["description"]}
                for slug in BLOG_POSTS
            ],
            "structured_data": base_structured_data(),
        }
    )
    return render_template("marketing.html", **context)


@app.route("/<lang>/faq")
def faq(lang):
    if lang not in SUPPORTED_LANGS:
        abort(404)
    page_title = "FAQ Fin-gram" if lang == "ru" else "Fin-gram FAQ"
    description = (
        "Ответы на частые вопросы о Fin-gram, Telegram Web App и учете личных финансов."
        if lang == "ru"
        else "Frequently asked questions about Fin-gram, Telegram Web App, and personal finance tracking."
    )
    structured_data = base_structured_data() + [
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": item["q"], "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                for item in FAQ_CONTENT[lang]
            ],
        }
    ]
    context = marketing_page_context(lang, page_title, description, f"{get_site_url()}/{lang}/faq", "/faq")
    context.update({"page_kind": "faq", "faq_items": FAQ_CONTENT[lang], "structured_data": structured_data})
    return render_template("faq.html", **context)


@app.route("/<lang>/about")
def about(lang):
    if lang not in SUPPORTED_LANGS:
        abort(404)
    content = ABOUT_CONTENT[lang]
    context = marketing_page_context(
        lang,
        content["title"],
        content["description"],
        f"{get_site_url()}/{lang}/about",
        "/about",
    )
    context.update({"page_kind": "about", "content": content, "structured_data": base_structured_data()})
    return render_template("about.html", **context)


@app.route("/<lang>/pricing")
def pricing(lang):
    if lang not in SUPPORTED_LANGS:
        abort(404)
    content = PRICING_CONTENT[lang]
    context = marketing_page_context(
        lang,
        content["title"],
        content["description"],
        f"{get_site_url()}/{lang}/pricing",
        "/pricing",
    )
    context.update({"page_kind": "pricing", "content": content, "structured_data": base_structured_data()})
    return render_template("pricing.html", **context)


@app.route("/<lang>/blog/<slug>")
def blog_article(lang, slug):
    if lang not in SUPPORTED_LANGS:
        abort(404)
    article_group = BLOG_POSTS.get(slug)
    if not article_group or lang not in article_group:
        abort(404)
    article = article_group[lang]
    canonical_url = f"{get_site_url()}/{lang}/blog/{slug}"
    structured_data = base_structured_data() + [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": article["title"],
            "description": article["description"],
            "author": {"@type": "Organization", "name": SITE_NAME},
            "publisher": {"@type": "Organization", "name": SITE_NAME},
            "mainEntityOfPage": canonical_url,
            "datePublished": "2026-03-28",
            "dateModified": "2026-03-28",
            "image": f"{get_site_url()}/static/og-fin-gram.svg",
            "inLanguage": lang,
        }
    ]
    context = marketing_page_context(
        lang,
        article["title"],
        article["description"],
        canonical_url,
        f"/blog/{slug}",
    )
    context.update({"page_kind": "article", "article": article, "slug": slug, "structured_data": structured_data})
    return render_template("article.html", **context)


@app.route("/robots.txt")
def robots_txt():
    site_url = get_site_url()
    content = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /app",
            "Disallow: /api/",
            "Sitemap: " + f"{site_url}/sitemap.xml",
        ]
    )
    response = make_response(content)
    response.mimetype = "text/plain"
    return response


@app.route("/sitemap.xml")
def sitemap():
    urls = [
        {"loc": f"{get_site_url()}/ru", "priority": "1.0"},
        {"loc": f"{get_site_url()}/en", "priority": "0.9"},
        {"loc": f"{get_site_url()}/ru/about", "priority": "0.8"},
        {"loc": f"{get_site_url()}/en/about", "priority": "0.8"},
        {"loc": f"{get_site_url()}/ru/pricing", "priority": "0.7"},
        {"loc": f"{get_site_url()}/en/pricing", "priority": "0.7"},
        {"loc": f"{get_site_url()}/ru/faq", "priority": "0.8"},
        {"loc": f"{get_site_url()}/en/faq", "priority": "0.8"},
    ]
    for slug in BLOG_POSTS:
        urls.append({"loc": f"{get_site_url()}/ru/blog/{slug}", "priority": "0.7"})
        urls.append({"loc": f"{get_site_url()}/en/blog/{slug}", "priority": "0.7"})
    response = make_response(render_template("sitemap.xml", urls=urls))
    response.mimetype = "application/xml"
    return response


@app.route("/api/me")
def me():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    touch_user_activity(user_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, email, display_name, telegram_user_id, preferred_currency,
               monthly_income_target, monthly_savings_goal, emergency_fund_target_months,
               last_seen_at
        FROM users WHERE id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "not_found"}), 404
    user = dict(row)
    user["preferred_currency"] = user.get("preferred_currency") or "USD"
    user["emergency_fund_target_months"] = user.get("emergency_fund_target_months") or 3
    return jsonify({"ok": True, "user": user})


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip() or email
    preferred_currency = (data.get("preferred_currency") or "USD").upper()
    if preferred_currency not in ALLOWED_CURRENCIES:
        preferred_currency = "USD"
    if not email or not password:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (email, password_hash, display_name, preferred_currency, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, generate_password_hash(password), display_name, preferred_currency, now_iso()),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "error": "email_exists"}), 409
    conn.close()
    session["user_id"] = user_id
    touch_user_activity(user_id)
    return jsonify({"ok": True})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"ok": False, "error": "missing_fields"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"ok": False, "error": "invalid_credentials"}), 401
    session["user_id"] = row["id"]
    touch_user_activity(row["id"])
    return jsonify({"ok": True})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.route("/api/auth/telegram", methods=["POST"])
def auth_telegram():
    data = request.get_json(force=True)
    init_data = data.get("initData") or ""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not verify_telegram_init_data(init_data, bot_token):
        return jsonify({"ok": False, "error": "invalid_init_data"}), 401
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    tg_user = parsed.get("user")
    if not tg_user:
        return jsonify({"ok": False, "error": "missing_user"}), 400
    try:
        tg_user_obj = json.loads(tg_user)
        tg_user_id = str(tg_user_obj.get("id"))
        display_name = tg_user_obj.get("first_name") or "Telegram User"
    except Exception:
        return jsonify({"ok": False, "error": "bad_user"}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE telegram_user_id = ?", (tg_user_id,))
    row = cur.fetchone()
    if row:
        user_id = row["id"]
    else:
        cur.execute(
            """
            INSERT INTO users (email, password_hash, display_name, telegram_user_id, preferred_currency, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (None, None, display_name, tg_user_id, "USD", now_iso()),
        )
        conn.commit()
        user_id = cur.lastrowid
    conn.close()
    session["user_id"] = user_id
    touch_user_activity(user_id)
    return jsonify({"ok": True, "user_id": user_id})


@app.route("/api/entries", methods=["GET", "POST"])
def entries():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    touch_user_activity(user_id)
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        data = request.get_json(force=True)
        entry_type = data.get("type")
        amount = data.get("amount")
        currency = (data.get("currency") or "").upper()
        if not currency or currency not in ALLOWED_CURRENCIES:
            currency = get_user_currency(cur, user_id)
        category = (data.get("category") or "").strip() or "Uncategorized"
        note = (data.get("note") or "").strip()
        occurred_at = normalize_entry_date(data.get("occurred_at"))
        if entry_type not in ("income", "expense"):
            conn.close()
            return jsonify({"ok": False, "error": "invalid_type"}), 400
        try:
            amount_val = float(amount)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"ok": False, "error": "invalid_amount"}), 400
        cur.execute(
            """
            INSERT INTO entries (user_id, type, amount, currency, category, note, occurred_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, entry_type, amount_val, currency, category, note, occurred_at, now_iso()),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    limit = request.args.get("limit")
    offset = request.args.get("offset")
    query = "SELECT * FROM entries WHERE user_id = ?"
    params = [user_id]
    if date_from:
        query += " AND substr(occurred_at, 1, 10) >= ?"
        params.append(normalize_entry_date(date_from))
    if date_to:
        query += " AND substr(occurred_at, 1, 10) <= ?"
        params.append(normalize_entry_date(date_to))
    query += " ORDER BY substr(occurred_at, 1, 10) DESC, created_at DESC"
    count_query = "SELECT COUNT(*) as total FROM entries WHERE user_id = ?"
    count_params = [user_id]
    if date_from:
        count_query += " AND substr(occurred_at, 1, 10) >= ?"
        count_params.append(normalize_entry_date(date_from))
    if date_to:
        count_query += " AND substr(occurred_at, 1, 10) <= ?"
        count_params.append(normalize_entry_date(date_to))
    if limit:
        try:
            limit_val = max(1, min(int(limit), 200))
        except ValueError:
            limit_val = 10
        offset_val = 0
        if offset:
            try:
                offset_val = max(0, int(offset))
            except ValueError:
                offset_val = 0
        query += " LIMIT ? OFFSET ?"
        params.extend([limit_val, offset_val])
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute(count_query, count_params)
    total = cur.fetchone()["total"]
    conn.close()
    return jsonify({"ok": True, "entries": rows, "total": total})


@app.route("/api/stats")
def stats():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    touch_user_activity(user_id)
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    conn = get_db()
    cur = conn.cursor()
    query = "SELECT type, SUM(amount) as total FROM entries WHERE user_id = ?"
    params = [user_id]
    if date_from:
        query += " AND substr(occurred_at, 1, 10) >= ?"
        params.append(normalize_entry_date(date_from))
    if date_to:
        query += " AND substr(occurred_at, 1, 10) <= ?"
        params.append(normalize_entry_date(date_to))
    query += " GROUP BY type"
    cur.execute(query, params)
    totals = {"income": 0.0, "expense": 0.0}
    for row in cur.fetchall():
        totals[row["type"]] = row["total"] or 0.0
    conn.close()
    totals["net"] = totals["income"] - totals["expense"]
    return jsonify({"ok": True, "totals": totals})


@app.route("/api/profile", methods=["GET", "PATCH"])
def profile():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    touch_user_activity(user_id)
    conn = get_db()
    cur = conn.cursor()
    if request.method == "PATCH":
        data = request.get_json(force=True)
        display_name = (data.get("display_name") or "").strip()
        preferred_currency = (data.get("preferred_currency") or "").upper()
        monthly_income_target = data.get("monthly_income_target")
        monthly_savings_goal = data.get("monthly_savings_goal")
        emergency_fund_target_months = data.get("emergency_fund_target_months")
        if preferred_currency and preferred_currency not in ALLOWED_CURRENCIES:
            conn.close()
            return jsonify({"ok": False, "error": "invalid_currency"}), 400
        if display_name:
            cur.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
        if preferred_currency:
            cur.execute("UPDATE users SET preferred_currency = ? WHERE id = ?", (preferred_currency, user_id))
        if monthly_income_target is not None:
            try:
                val = float(monthly_income_target)
                cur.execute("UPDATE users SET monthly_income_target = ? WHERE id = ?", (val, user_id))
            except (TypeError, ValueError):
                pass
        if monthly_savings_goal is not None:
            try:
                val = float(monthly_savings_goal)
                cur.execute("UPDATE users SET monthly_savings_goal = ? WHERE id = ?", (val, user_id))
            except (TypeError, ValueError):
                pass
        if emergency_fund_target_months is not None:
            try:
                val = float(emergency_fund_target_months)
                cur.execute(
                    "UPDATE users SET emergency_fund_target_months = ? WHERE id = ?",
                    (val, user_id),
                )
            except (TypeError, ValueError):
                pass
        conn.commit()
    cur.execute(
        """
        SELECT id, email, display_name, preferred_currency,
               monthly_income_target, monthly_savings_goal, emergency_fund_target_months,
               last_seen_at
        FROM users WHERE id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    user = dict(row) if row else {}
    if user and not user.get("preferred_currency"):
        user["preferred_currency"] = "USD"
    if user and not user.get("emergency_fund_target_months"):
        user["emergency_fund_target_months"] = 3
    return jsonify({"ok": True, "user": user})


@app.route("/api/analytics")
def analytics():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    touch_user_activity(user_id)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    month_start, month_end = month_range_utc(now)
    month_start_day = month_start.date().isoformat()
    month_end_day = (month_end.date() - timedelta(days=1)).isoformat()
    seven_days_ago = (now - timedelta(days=6)).date().isoformat()
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT category, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'expense' AND substr(occurred_at, 1, 10) = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, today),
    )
    today_categories = [
        {"category": row["category"], "total": row["total"] or 0.0} for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT type, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
        GROUP BY type
        """,
        (user_id, month_start_day, month_end_day),
    )
    month_totals = {"income": 0.0, "expense": 0.0}
    for row in cur.fetchall():
        month_totals[row["type"]] = row["total"] or 0.0
    month_totals["net"] = month_totals["income"] - month_totals["expense"]

    cur.execute(
        """
        SELECT category, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'expense' AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 6
        """,
        (user_id, month_start_day, month_end_day),
    )
    month_top_categories = [
        {"category": row["category"], "total": row["total"] or 0.0} for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT category, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'income' AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 6
        """,
        (user_id, month_start_day, month_end_day),
    )
    month_income_categories = [
        {"category": row["category"], "total": row["total"] or 0.0} for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT substr(occurred_at, 1, 10) as day, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'expense' AND substr(occurred_at, 1, 10) >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (user_id, seven_days_ago),
    )
    last_7_days = [{"day": row["day"], "total": row["total"] or 0.0} for row in cur.fetchall()]

    # cashflow series (last 30 days)
    start_30 = (now - timedelta(days=29)).date()
    cur.execute(
        """
        SELECT substr(occurred_at, 1, 10) as day, type, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND substr(occurred_at, 1, 10) >= ?
        GROUP BY day, type
        ORDER BY day ASC
        """,
        (user_id, start_30.isoformat()),
    )
    day_map = {}
    for row in cur.fetchall():
        day = row["day"]
        if day not in day_map:
            day_map[day] = {"income": 0.0, "expense": 0.0}
        day_map[day][row["type"]] = row["total"] or 0.0
    cashflow_series = []
    for i in range(30):
        d = (start_30 + timedelta(days=i)).isoformat()
        values = day_map.get(d, {"income": 0.0, "expense": 0.0})
        cashflow_series.append({"day": d, "income": values["income"], "expense": values["expense"]})

    months = []
    for i in range(5, -1, -1):
        dt = now - timedelta(days=30 * i)
        months.append((dt.year, dt.month))
    seen = []
    for year, month in months:
        if (year, month) not in seen:
            seen.append((year, month))
    month_series = []
    for year, month in seen:
        start, end = month_start_end(year, month)
        cur.execute(
            """
            SELECT type, SUM(amount) as total
            FROM entries
            WHERE user_id = ? AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
            GROUP BY type
            """,
            (user_id, start.date().isoformat(), (end.date() - timedelta(days=1)).isoformat()),
        )
        totals = {"income": 0.0, "expense": 0.0}
        for row in cur.fetchall():
            totals[row["type"]] = row["total"] or 0.0
        label = f"{year}-{month:02d}"
        month_series.append({"month": label, "income": totals["income"], "expense": totals["expense"]})

    prev_start, prev_end = month_start_end(month_start.year, month_start.month - 1 if month_start.month > 1 else 12)
    if month_start.month == 1:
        prev_start = datetime(year=month_start.year - 1, month=12, day=1, tzinfo=timezone.utc)
        prev_end = datetime(year=month_start.year, month=1, day=1, tzinfo=timezone.utc)
    cur.execute(
        """
        SELECT type, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
        GROUP BY type
        """,
        (user_id, prev_start.date().isoformat(), (prev_end.date() - timedelta(days=1)).isoformat()),
    )
    prev_totals = {"income": 0.0, "expense": 0.0}
    for row in cur.fetchall():
        prev_totals[row["type"]] = row["total"] or 0.0
    month_comparison = {
        "income_diff": month_totals["income"] - prev_totals["income"],
        "expense_diff": month_totals["expense"] - prev_totals["expense"],
        "net_diff": month_totals["net"] - (prev_totals["income"] - prev_totals["expense"]),
    }

    # concentration metrics
    total_expense = month_totals["expense"] or 0.0
    hhi_expense = 0.0
    top_expense_share = 0.0
    if total_expense > 0:
        if month_top_categories:
            top_expense_share = (month_top_categories[0]["total"] or 0.0) / total_expense
        for cat in month_top_categories:
            share = (cat["total"] or 0.0) / total_expense
            hhi_expense += share * share

    total_income = month_totals["income"] or 0.0
    hhi_income = 0.0
    if total_income > 0:
        for cat in month_income_categories:
            share = (cat["total"] or 0.0) / total_income
            hhi_income += share * share

    savings_rate = 0.0
    expense_ratio = 0.0
    if total_income > 0:
        savings_rate = month_totals["net"] / total_income
        expense_ratio = total_expense / total_income

    avg_daily_expense = total_expense / max(1, (month_end - month_start).days)
    avg_daily_income = total_income / max(1, (month_end - month_start).days)

    # emergency fund estimate based on last 3 months net and avg expense
    three_month_start = month_start - timedelta(days=90)
    cur.execute(
        """
        SELECT type, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND substr(occurred_at, 1, 10) >= ? AND substr(occurred_at, 1, 10) <= ?
        GROUP BY type
        """,
        (user_id, three_month_start.date().isoformat(), month_end_day),
    )
    totals_3m = {"income": 0.0, "expense": 0.0}
    for row in cur.fetchall():
        totals_3m[row["type"]] = row["total"] or 0.0
    net_3m = totals_3m["income"] - totals_3m["expense"]
    avg_monthly_expense = totals_3m["expense"] / 3.0 if totals_3m["expense"] else 0.0
    emergency_fund_months = (net_3m / avg_monthly_expense) if avg_monthly_expense > 0 else 0.0

    # goals
    cur.execute(
        """
        SELECT monthly_income_target, monthly_savings_goal, emergency_fund_target_months
        FROM users WHERE id = ?
        """,
        (user_id,),
    )
    goal_row = cur.fetchone() or {}
    income_target = goal_row["monthly_income_target"] if goal_row else None
    savings_goal = goal_row["monthly_savings_goal"] if goal_row else None
    ef_target = goal_row["emergency_fund_target_months"] if goal_row else 3

    advice = []
    if savings_rate < 0.1 and total_income > 0:
        advice.append("Сначала откладывайте фиксированную долю дохода (10–20%), затем планируйте расходы.")
    if ef_target and emergency_fund_months < ef_target:
        advice.append("Увеличьте подушку безопасности до заданного числа месяцев расходов.")
    if hhi_income > 0.6 and total_income > 0:
        advice.append("Доходы сильно зависят от одного источника — подумайте о диверсификации.")
    if top_expense_share > 0.4 and total_expense > 0:
        advice.append("Одна категория расходов занимает большую долю — установите лимит на месяц.")
    if not advice:
        advice.append("Продолжайте регулярно фиксировать операции — это улучшает контроль и прогнозирование.")

    conn.close()
    return jsonify(
        {
            "ok": True,
            "today_categories": today_categories,
            "month_totals": month_totals,
            "month_top_categories": month_top_categories,
            "month_income_categories": month_income_categories,
            "last_7_days": last_7_days,
            "month_series": month_series,
            "month_comparison": month_comparison,
            "cashflow_series": cashflow_series,
            "savings_rate": savings_rate,
            "expense_ratio": expense_ratio,
            "avg_daily_expense": avg_daily_expense,
            "avg_daily_income": avg_daily_income,
            "top_expense_share": top_expense_share,
            "expense_hhi": hhi_expense,
            "income_hhi": hhi_income,
            "emergency_fund_months": emergency_fund_months,
            "emergency_fund_target_months": ef_target,
            "monthly_income_target": income_target,
            "monthly_savings_goal": savings_goal,
            "advice": advice,
        }
    )


@app.route("/api/config")
def config():
    return jsonify(
        {
            "ok": True,
            "telegram": {
                "bot_username": os.environ.get("TELEGRAM_BOT_USERNAME", ""),
                "webapp_url": os.environ.get("TELEGRAM_WEBAPP_URL", ""),
            },
        }
    )


@app.route("/static/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
