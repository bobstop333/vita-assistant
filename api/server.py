"""
VITA Assistant — FastAPI backend для Telegram Mini App.
Порт: 8001 (проксируется nginx на /api)
"""
import hashlib
import hmac
import json
import logging
import os
import urllib.parse
from datetime import date

import aiosqlite
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Конфиг ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
DB_PATH   = os.getenv("DB_PATH", "/root/vita_bot/database.db")

ALLOWED_ORIGINS = [
    "https://bobstop333.github.io",
    "https://web.telegram.org",
    "http://localhost",        # для локальной отладки
    "null",                    # Telegram открывает как file://
]

app = FastAPI(title="VITA API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── Валидация Telegram initData ──────────────────────────────────────────────
def validate_init_data(init_data_raw: str, bot_token: str) -> dict:
    """
    Проверяет подпись initData по алгоритму из документации Telegram:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Возвращает распарсенные данные или бросает ValueError.
    """
    parsed = urllib.parse.parse_qs(init_data_raw, keep_blank_values=True)
    # parse_qs возвращает списки — берём первое значение каждого ключа
    flat = {k: v[0] for k, v in parsed.items()}

    received_hash = flat.pop("hash", None)
    if not received_hash:
        raise ValueError("hash missing")

    # Строим data_check_string: пары key=value, отсортированные по ключу, через \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(flat.items())
    )

    # secret_key = HMAC-SHA256(bot_token, key="WebAppData")
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    # expected_hash = HMAC-SHA256(data_check_string, key=secret_key)
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("hash mismatch")

    return flat


def extract_telegram_id(flat: dict) -> int:
    """Достаёт telegram_id из поля 'user' (JSON-строка)."""
    user_json = flat.get("user", "{}")
    user_data = json.loads(user_json)
    uid = user_data.get("id")
    if not uid:
        raise ValueError("user.id not found")
    return int(uid)


# ── Helpers для КБЖУ ────────────────────────────────────────────────────────
def _calc_plan(weight, height, age, gender, goal, activity="moderate"):
    """Упрощённая копия services/nutrition.py — без внешних зависимостей."""
    if gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    factors = {
        "sedentary": 1.2, "light": 1.375, "moderate": 1.55,
        "active": 1.725, "very_active": 1.9,
    }
    tdee = bmr * factors.get(activity, 1.55)

    goal_l = goal.lower()
    if "похудение" in goal_l or "pohud" in goal_l:
        calories = tdee - 500
    elif "набор" in goal_l or "mass" in goal_l:
        calories = tdee + 300
    else:
        calories = tdee

    calories = int(calories)
    protein  = int(weight * 2)
    fat      = int(weight * 1)
    carbs    = max(0, int((calories - protein * 4 - fat * 9) / 4))

    return {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}


# ── Роуты ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/user-data")
async def user_data(request: Request):
    """
    Принимает ?initData=... (или заголовок X-Init-Data).
    Валидирует подпись, возвращает КБЖУ за сегодня.
    """
    # Получаем initData из query-параметра или заголовка
    init_data_raw = (
        request.query_params.get("initData")
        or request.headers.get("X-Init-Data", "")
    )

    if not init_data_raw:
        raise HTTPException(status_code=400, detail="initData required")

    # Валидация
    try:
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN not set on server")
        flat = validate_init_data(init_data_raw, BOT_TOKEN)
        telegram_id = extract_telegram_id(flat)
    except ValueError as e:
        logger.warning(f"Auth failed: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Данные из БД
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT weight, height, age, gender, goal, activity_level FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        user = await cursor.fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="Profile not found. Please /start the bot first.")

        weight, height, age, gender, goal, activity = user
        activity = activity or "moderate"

        # Съеденное за сегодня
        cursor = await db.execute(
            """SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs)
               FROM meals
               WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')""",
            (telegram_id,)
        )
        row = await cursor.fetchone()

        # Последний записанный вес
        cursor = await db.execute(
            "SELECT weight FROM weight_logs WHERE telegram_id = ? ORDER BY date DESC LIMIT 1",
            (telegram_id,)
        )
        last_weight_row = await cursor.fetchone()
        current_weight = last_weight_row[0] if last_weight_row else weight

    plan = _calc_plan(weight, height, age, gender, goal, activity)

    cal_cur = int(row[0] or 0)
    pro_cur = int(row[1] or 0)
    fat_cur = int(row[2] or 0)
    car_cur = int(row[3] or 0)

    progress = min(100, int(cal_cur / plan["calories"] * 100)) if plan["calories"] else 0

    return {
        "telegram_id":       telegram_id,
        "goal":              goal,
        "calories_current":  cal_cur,
        "calories_target":   plan["calories"],
        "protein_current":   pro_cur,
        "protein_target":    plan["protein"],
        "fat_current":       fat_cur,
        "fat_target":        plan["fat"],
        "carbs_current":     car_cur,
        "carbs_target":      plan["carbs"],
        "progress_percent":  progress,
        "current_weight":    current_weight,
        "date":              str(date.today()),
    }
