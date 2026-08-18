import asyncio
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.ai import ask_ai
from services.nutrition import calculate_plan
import aiosqlite

router = Router()
DB = "database.db"


def food_keyboard():
    """Клавиатура дневника питания — используется и из menu, и из food.py."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить текстом", callback_data="food_add_text")],
        [InlineKeyboardButton(text="📸 Добавить фото",   callback_data="food_add_photo")],
        [InlineKeyboardButton(text="📋 История за день", callback_data="food_history")],
    ])


@router.message(F.text == "🥗 Расчет рациона")
async def food_summary(message: types.Message):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT weight, height, age, gender, goal, activity_level FROM users WHERE telegram_id = ?",
            (message.from_user.id,)
        )
        user = await cursor.fetchone()

        if not user:
            return await message.answer("⚠️ Сначала заполни профиль через *🚀 Начать*", parse_mode="Markdown")

        weight, height, age, gender, goal, activity = user
        activity = activity or "moderate"
        plan = calculate_plan(weight, height, age, gender, goal, activity)
        target_cal = plan["calories"]

        cursor = await db.execute(
            "SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs) FROM meals "
            "WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')",
            (message.from_user.id,)
        )
        row = await cursor.fetchone()

    eaten_cal = row[0] or 0
    eaten_p   = row[1] or 0
    eaten_f   = row[2] or 0
    eaten_c   = row[3] or 0

    percent = min(100, int((eaten_cal / target_cal) * 100)) if target_cal else 0
    filled  = int(percent / 10)
    bar     = "█" * filled + "░" * (10 - filled)

    text = (
        f"🍽 *Дневник питания*\n\n"
        f"📊 Прогресс: {percent}%\n"
        f"`[{bar}]` {eaten_cal} / {target_cal} ккал\n\n"
        f"🥩 Белки: {eaten_p} / {plan['protein']} г\n"
        f"🥑 Жиры: {eaten_f} / {plan['fat']} г\n"
        f"🍞 Углеводы: {eaten_c} / {plan['carbs']} г\n\n"
        f"Как добавим еду?"
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=food_keyboard())


# ──────────────────────────────────────────────────────
# Вода
# ──────────────────────────────────────────────────────
def get_water_keyboard(total: int = 0):
    goal = 2000
    percent = min(100, int(total / goal * 100))
    filled = int(percent / 10)
    bar = "💧" * filled + "○" * (10 - filled)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💧 +250 мл", callback_data="water_250"),
            InlineKeyboardButton(text="🥤 +500 мл", callback_data="water_500"),
            InlineKeyboardButton(text="🍶 +1000 мл", callback_data="water_1000")
        ],
        [InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_message")]
    ])


def water_text(total: int) -> str:
    goal = 2000
    percent = min(100, int(total / goal * 100))
    filled = int(percent / 10)
    bar = "💧" * filled + "○" * (10 - filled)
    status = "✅ Цель выполнена! 🎉" if total >= goal else f"Осталось: {goal - total} мл"
    return (
        f"🚰 *Трекер воды*\n\n"
        f"`[{bar}]` {percent}%\n"
        f"Выпито: *{total} мл* / {goal} мл\n\n"
        f"{status}\n\n"
        f"Отмечай каждый стакан воды!"
    )


@router.message(F.text == "💧 Вода")
async def water_handler(message: types.Message):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT SUM(amount_ml) FROM water_logs WHERE telegram_id = ? AND date = date('now', 'localtime')",
            (message.from_user.id,)
        )
        total_water = (await cursor.fetchone())[0] or 0

    await message.answer(water_text(total_water), reply_markup=get_water_keyboard(total_water), parse_mode="Markdown")


@router.callback_query(F.data.startswith("water_"))
async def process_water(callback: types.CallbackQuery):
    amount = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO water_logs (telegram_id, amount_ml) VALUES (?, ?)",
            (callback.from_user.id, amount)
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT SUM(amount_ml) FROM water_logs WHERE telegram_id = ? AND date = date('now', 'localtime')",
            (callback.from_user.id,)
        )
        total_water = (await cursor.fetchone())[0] or 0

    try:
        await callback.message.edit_text(
            water_text(total_water),
            reply_markup=get_water_keyboard(total_water),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await callback.answer(f"+{amount} мл записано! 💧")


# ──────────────────────────────────────────────────────
# Закрыть сообщение
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "close_message")
async def close_message_handler(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# ──────────────────────────────────────────────────────
# ИИ-чат (свободный ввод)
# ──────────────────────────────────────────────────────
@router.message()
async def ai_handler(message: types.Message):
    if message.text and not message.text.startswith("/"):
        msg = await message.answer("🤔 Думаю...")
        # asyncio.to_thread — запускаем синхронную функцию в пуле потоков
        response = await asyncio.to_thread(ask_ai, message.text)
        await msg.edit_text(response)