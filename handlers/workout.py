import asyncio
import aiosqlite
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.ai import generate_workout

router = Router()
DB = "database.db"


# ──────────────────────────────────────────────────────
# Клавиатуры
# ──────────────────────────────────────────────────────
def location_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Дома",   callback_data="workout_home"),
            InlineKeyboardButton(text="💪 В зале", callback_data="workout_gym")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="workout_close")]
    ])


def refresh_keyboard(location_key: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другая тренировка", callback_data=f"workout_{location_key}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="workout_back")]
    ])


# ──────────────────────────────────────────────────────
# Кнопка «Назад» — возврат к выбору локации
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "workout_back")
async def workout_back(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT goal FROM users WHERE telegram_id = ?",
            (callback.from_user.id,)
        )
        user = await cursor.fetchone()

    if not user:
        await callback.answer("Сначала заполни профиль!", show_alert=True)
        return

    await callback.message.edit_text(
        "🏋️ *Тренировка дня*\n\nГде будешь заниматься?",
        parse_mode="Markdown",
        reply_markup=location_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "workout_close")
async def workout_close(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# ──────────────────────────────────────────────────────
# Вход: нажатие кнопки «🏋️ Тренировки»
# ──────────────────────────────────────────────────────
@router.message(F.text == "🏋️ Тренировки")
async def workout_handler(message: types.Message):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT goal FROM users WHERE telegram_id = ?",
            (message.from_user.id,)
        )
        user = await cursor.fetchone()

    if not user:
        await message.answer(
            "⚠️ Сначала заполни профиль через *🚀 Начать*, "
            "чтобы тренировки подбирались под твою цель!",
            parse_mode="Markdown"
        )
        return

    await message.answer(
        "🏋️ *Тренировка дня*\n\nГде будешь заниматься?",
        parse_mode="Markdown",
        reply_markup=location_keyboard()
    )


# ──────────────────────────────────────────────────────
# Генерация тренировки
# ──────────────────────────────────────────────────────
@router.callback_query(F.data.in_({"workout_home", "workout_gym"}))
async def generate_workout_plan(callback: types.CallbackQuery):
    location_map = {"workout_home": "дома", "workout_gym": "в зале"}
    location_key = callback.data.split("_")[1]   # "home" или "gym"
    location     = location_map[callback.data]

    # Получаем цель пользователя
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT goal FROM users WHERE telegram_id = ?",
            (callback.from_user.id,)
        )
        row  = await cursor.fetchone()
        goal = row[0] if row else "поддержание"

    await callback.message.edit_text(
        f"⏳ Генерирую тренировку {location}...\nЭто займёт 5-10 секунд 🤖"
    )

    # asyncio.to_thread — запускаем синхронный Gemini-вызов в пуле потоков
    plan = await asyncio.to_thread(generate_workout, goal, location)

    # Сохраняем в лог
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO workout_logs (telegram_id, plan, location) VALUES (?, ?, ?)",
            (callback.from_user.id, plan, location)
        )
        await db.commit()

    loc_emoji = "🏠" if location == "дома" else "💪"
    header    = f"{loc_emoji} *Тренировка {location}* | Цель: _{goal}_\n\n"

    await callback.message.edit_text(
        header + plan,
        parse_mode="Markdown",
        reply_markup=refresh_keyboard(location_key)
    )
    await callback.answer()
