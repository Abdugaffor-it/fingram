import os
import sqlite3
import json
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qsl
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.environ.get("APP_SECRET", "dev-secret-change-me")
ALLOWED_CURRENCIES = {"TJS", "RUB", "USD", "KZT", "UZS"}


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
    cur.execute("UPDATE users SET preferred_currency = COALESCE(preferred_currency, 'USD')")
    cur.execute(
        "UPDATE users SET emergency_fund_target_months = COALESCE(emergency_fund_target_months, 3)"
    )
    conn.commit()
    conn.close()

init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat()

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


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/me")
def me():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, email, display_name, telegram_user_id, preferred_currency,
               monthly_income_target, monthly_savings_goal, emergency_fund_target_months
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
    return jsonify({"ok": True, "user_id": user_id})


@app.route("/api/entries", methods=["GET", "POST"])
def entries():
    user_id = require_auth()
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
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
        occurred_at = data.get("occurred_at") or now_iso()
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
        query += " AND occurred_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND occurred_at <= ?"
        params.append(date_to)
    query += " ORDER BY occurred_at DESC"
    count_query = "SELECT COUNT(*) as total FROM entries WHERE user_id = ?"
    count_params = [user_id]
    if date_from:
        count_query += " AND occurred_at >= ?"
        count_params.append(date_from)
    if date_to:
        count_query += " AND occurred_at <= ?"
        count_params.append(date_to)
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
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    conn = get_db()
    cur = conn.cursor()
    query = "SELECT type, SUM(amount) as total FROM entries WHERE user_id = ?"
    params = [user_id]
    if date_from:
        query += " AND occurred_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND occurred_at <= ?"
        params.append(date_to)
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
               monthly_income_target, monthly_savings_goal, emergency_fund_target_months
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
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    month_start, month_end = month_range_utc(now)
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
        WHERE user_id = ? AND occurred_at >= ? AND occurred_at < ?
        GROUP BY type
        """,
        (user_id, month_start.isoformat(), month_end.isoformat()),
    )
    month_totals = {"income": 0.0, "expense": 0.0}
    for row in cur.fetchall():
        month_totals[row["type"]] = row["total"] or 0.0
    month_totals["net"] = month_totals["income"] - month_totals["expense"]

    cur.execute(
        """
        SELECT category, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'expense' AND occurred_at >= ? AND occurred_at < ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 6
        """,
        (user_id, month_start.isoformat(), month_end.isoformat()),
    )
    month_top_categories = [
        {"category": row["category"], "total": row["total"] or 0.0} for row in cur.fetchall()
    ]

    cur.execute(
        """
        SELECT category, SUM(amount) as total
        FROM entries
        WHERE user_id = ? AND type = 'income' AND occurred_at >= ? AND occurred_at < ?
        GROUP BY category
        ORDER BY total DESC
        LIMIT 6
        """,
        (user_id, month_start.isoformat(), month_end.isoformat()),
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
            WHERE user_id = ? AND occurred_at >= ? AND occurred_at < ?
            GROUP BY type
            """,
            (user_id, start.isoformat(), end.isoformat()),
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
        WHERE user_id = ? AND occurred_at >= ? AND occurred_at < ?
        GROUP BY type
        """,
        (user_id, prev_start.isoformat(), prev_end.isoformat()),
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
        WHERE user_id = ? AND occurred_at >= ? AND occurred_at < ?
        GROUP BY type
        """,
        (user_id, three_month_start.isoformat(), month_end.isoformat()),
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
