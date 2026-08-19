"""
VITA Assistant — FastAPI backend для Telegram Mini App.
Порт: 8001 (проксируется nginx на /api)
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import urllib.parse
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Явно указываем путь к .env — сервис может запускаться не из папки проекта
_env_path = Path("/root/vita_bot/.env")
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()  # fallback: ищем .env в текущей директории

import aiosqlite
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Конфиг ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH   = os.getenv("DB_PATH", "/root/vita_bot/database.db")

ALLOWED_ORIGINS = [
    "https://bobstop333.github.io",
    "https://web.telegram.org",
    "http://localhost",
    "null",                    # Telegram открывает как file://
]

app = FastAPI(title="VITA API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Добавляем корень проекта в sys.path, чтобы импортировать services.ai ───
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Валидация Telegram initData ──────────────────────────────────────────────
def validate_init_data(init_data_raw: str, bot_token: str) -> dict:
    """
    Проверяет подпись initData по алгоритму из документации Telegram:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    Возвращает распарсенные данные или бросает ValueError.
    """
    parsed = urllib.parse.parse_qs(init_data_raw, keep_blank_values=True)
    flat = {k: v[0] for k, v in parsed.items()}

    received_hash = flat.pop("hash", None)
    if not received_hash:
        raise ValueError("hash missing")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(flat.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
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


async def _get_telegram_id(request: Request) -> int:
    """Общий хелпер: извлекает и валидирует initData, возвращает telegram_id."""
    init_data_raw = (
        request.query_params.get("initData")
        or request.headers.get("X-Init-Data", "")
    )
    if not init_data_raw:
        raise HTTPException(status_code=400, detail="initData required")
    try:
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN not set on server")
        flat = validate_init_data(init_data_raw, BOT_TOKEN)
        return extract_telegram_id(flat)
    except ValueError as e:
        logger.warning(f"Auth failed: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Helpers для КБЖУ ────────────────────────────────────────────────────────
def _calc_plan(weight, height, age, gender, goal, activity="moderate"):
    """Рассчитывает дневной план КБЖУ (без внешних зависимостей)."""
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


# ════════════════════════════════════════════════════════════════════════════
# РОУТЫ
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Существующий эндпоинт ───────────────────────────────────────────────────
@app.get("/api/user-data")
async def user_data(request: Request):
    """Возвращает профиль пользователя + КБЖУ за сегодня."""
    telegram_id = await _get_telegram_id(request)

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

        cursor = await db.execute(
            """SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs)
               FROM meals
               WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')""",
            (telegram_id,)
        )
        row = await cursor.fetchone()

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


# ── Новые эндпоинты для Mini App ─────────────────────────────────────────────

@app.post("/api/analyze-food-photo")
async def analyze_food_photo_endpoint(request: Request):
    """
    Принимает JSON: { "image_base64": "...", "mime_type": "image/jpeg" }
    Возвращает КБЖУ распознанного блюда через Gemini Vision.
    """
    await _get_telegram_id(request)   # авторизация

    body      = await request.json()
    image_b64 = body.get("image_base64", "")

    if not image_b64:
        raise HTTPException(status_code=400, detail="image_base64 required")

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 data")

    from services.ai import analyze_food_photo

    result = await asyncio.to_thread(analyze_food_photo, image_bytes)

    if not result:
        raise HTTPException(status_code=422, detail="Could not recognize food in the image")

    return result


@app.post("/api/save-meal")
async def save_meal(request: Request):
    """
    Сохраняет приём пищи.
    Тело: { "name": str, "calories": int, "protein": int, "fat": int, "carbs": int }
    """
    telegram_id = await _get_telegram_id(request)

    body     = await request.json()
    name     = body.get("name", "")
    calories = int(body.get("calories", 0))
    protein  = int(body.get("protein", 0))
    fat      = int(body.get("fat", 0))
    carbs    = int(body.get("carbs", 0))

    if not name:
        raise HTTPException(status_code=400, detail="name required")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO meals (telegram_id, description, calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, name, calories, protein, fat, carbs)
        )
        await db.commit()

    return {"ok": True, "saved": {"name": name, "calories": calories}}


@app.get("/api/meals-today")
async def meals_today(request: Request):
    """Список приёмов пищи за сегодня + суммарные КБЖУ."""
    telegram_id = await _get_telegram_id(request)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT id, description, calories, protein, fat, carbs,
                      strftime('%H:%M', timestamp, 'localtime') as time
               FROM meals
               WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')
               ORDER BY timestamp ASC""",
            (telegram_id,)
        )
        rows = await cursor.fetchall()

    meals = [
        {
            "id":       r[0],
            "name":     r[1],
            "calories": r[2] or 0,
            "protein":  r[3] or 0,
            "fat":      r[4] or 0,
            "carbs":    r[5] or 0,
            "time":     r[6],
        }
        for r in rows
    ]

    totals = {
        "calories": sum(m["calories"] for m in meals),
        "protein":  sum(m["protein"]  for m in meals),
        "fat":      sum(m["fat"]      for m in meals),
        "carbs":    sum(m["carbs"]    for m in meals),
    }

    return {"meals": meals, "totals": totals}


@app.get("/api/weight-history")
async def weight_history(request: Request):
    """История веса за последние 30 дней для SVG-графика."""
    telegram_id = await _get_telegram_id(request)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT weight, date FROM weight_logs WHERE telegram_id = ? ORDER BY date ASC LIMIT 30",
            (telegram_id,)
        )
        rows = await cursor.fetchall()

        cursor = await db.execute(
            "SELECT weight, goal FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        user = await cursor.fetchone()

    return {
        "records":      [{"weight": r[0], "date": r[1]} for r in rows],
        "start_weight": user[0] if user else None,
        "goal":         user[1] if user else None,
    }


@app.post("/api/save-weight")
async def save_weight(request: Request):
    """
    Записывает текущий вес.
    Тело: { "weight": float }
    """
    telegram_id = await _get_telegram_id(request)

    body = await request.json()
    try:
        weight = float(body.get("weight", 0))
        assert 20 <= weight <= 400
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid weight value (20–400 kg)")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO weight_logs (telegram_id, weight) VALUES (?, ?)",
            (telegram_id, weight)
        )
        await db.commit()

    return {"ok": True, "weight": weight, "date": str(date.today())}


@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    ИИ-чат по ЗОЖ.
    Тело: { "message": str }
    Возвращает: { "reply": str }
    """
    await _get_telegram_id(request)   # авторизация

    body    = await request.json()
    message = body.get("message", "").strip()

    if not message:
        raise HTTPException(status_code=400, detail="message required")

    from services.ai import ask_ai

    reply = await asyncio.to_thread(ask_ai, message)

    return {"reply": reply}
