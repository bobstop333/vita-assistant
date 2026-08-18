from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.nutrition import calculate_plan
from services.ai import generate_meal_with_ai
import asyncio
import aiosqlite

router = Router()

class Form(StatesGroup):
    gender = State()
    age = State()
    weight = State()
    height = State()
    activity = State()
    goal = State()


# ────────────────────────────────────────────────────
# Старт онбординга
# ────────────────────────────────────────────────────
@router.message(F.text == "🚀 Начать")
async def start_onboarding(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male")],
        [InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female")]
    ])
    await message.answer(
        "👋 Привет! Давай настроим твой профиль — это займёт меньше минуты.\n\n"
        "🔹 Шаг 1/5: Выбери пол:",
        reply_markup=keyboard
    )
    await state.set_state(Form.gender)


@router.callback_query(Form.gender, F.data.startswith("gender_"))
async def process_gender(callback: types.CallbackQuery, state: FSMContext):
    gender = "male" if callback.data == "gender_male" else "female"
    await state.update_data(gender=gender)
    await callback.message.edit_text("🔹 Шаг 2/5: Напиши свой возраст (например, 25):")
    await state.set_state(Form.age)
    await callback.answer()


@router.message(Form.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введи число (например, 25).")
    age = int(message.text)
    if not (10 <= age <= 100):
        return await message.answer("Введи реальный возраст от 10 до 100.")
    await state.update_data(age=age)
    await message.answer("🔹 Шаг 3/5: Какой у тебя вес в кг? (например, 70)")
    await state.set_state(Form.weight)


@router.message(Form.weight)
async def process_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        assert 30 <= weight <= 300
    except Exception:
        return await message.answer("Введи реальный вес от 30 до 300 кг.")
    await state.update_data(weight=int(weight))
    await message.answer("🔹 Шаг 4/5: Какой у тебя рост в см? (например, 175)")
    await state.set_state(Form.height)


@router.message(Form.height)
async def process_height(message: types.Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        assert 100 <= height <= 250
    except Exception:
        return await message.answer("Введи реальный рост от 100 до 250 см.")
    await state.update_data(height=int(height))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛋 Сидячий (офис, без спорта)", callback_data="activity_sedentary")],
        [InlineKeyboardButton(text="🚶 Лёгкая (1-3 тренировки/нед)", callback_data="activity_light")],
        [InlineKeyboardButton(text="🏃 Умеренная (3-5 тренировок/нед)", callback_data="activity_moderate")],
        [InlineKeyboardButton(text="💪 Высокая (6-7 тренировок/нед)", callback_data="activity_active")],
        [InlineKeyboardButton(text="🔥 Атлет (2x в день / физ. труд)", callback_data="activity_very_active")],
    ])
    await message.answer("🔹 Шаг 5/5: Выбери уровень физической активности:", reply_markup=keyboard)
    await state.set_state(Form.activity)


@router.callback_query(Form.activity, F.data.startswith("activity_"))
async def process_activity(callback: types.CallbackQuery, state: FSMContext):
    activity = callback.data.replace("activity_", "")
    await state.update_data(activity=activity)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Похудение", callback_data="goal_pohud")],
        [InlineKeyboardButton(text="💪 Набор массы", callback_data="goal_mass")],
        [InlineKeyboardButton(text="⚖️ Поддержание формы", callback_data="goal_maintain")]
    ])
    await callback.message.edit_text("🎯 Отлично! Какая твоя цель?", reply_markup=keyboard)
    await state.set_state(Form.goal)
    await callback.answer()


@router.callback_query(Form.goal, F.data.startswith("goal_"))
async def process_goal(callback: types.CallbackQuery, state: FSMContext):
    goal_map = {
        "goal_pohud":    "похудение",
        "goal_mass":     "набор массы",
        "goal_maintain": "поддержание"
    }
    goal = goal_map.get(callback.data, "поддержание")
    data = await state.get_data()

    activity = data.get("activity", "moderate")
    plan = calculate_plan(
        weight=data["weight"],
        height=data["height"],
        age=data["age"],
        gender=data["gender"],
        goal=goal,
        activity_level=activity
    )

    async with aiosqlite.connect("database.db") as db:
        await db.execute(
            """INSERT INTO users (telegram_id, gender, age, weight, height, goal, activity_level)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
               gender=excluded.gender, age=excluded.age, weight=excluded.weight,
               height=excluded.height, goal=excluded.goal, activity_level=excluded.activity_level""",
            (callback.from_user.id, data["gender"], data["age"], data["weight"], data["height"], goal, activity)
        )
        await db.commit()

    activity_labels = {
        "sedentary":   "🛋 Сидячий",
        "light":       "🚶 Лёгкая",
        "moderate":    "🏃 Умеренная",
        "active":      "💪 Высокая",
        "very_active": "🔥 Атлет",
    }
    activity_label = activity_labels.get(activity, "Умеренная")

    await callback.message.edit_text(
        f"✅ *Профиль настроен!*\n\n"
        f"🎯 Цель: *{goal.capitalize()}*\n"
        f"⚡ Активность: *{activity_label}*\n\n"
        f"📊 *Твои ежедневные нормы:*\n"
        f"🔥 Калории: *{plan['calories']} ккал*\n"
        f"🥩 Белки: *{plan['protein']} г*\n"
        f"🥑 Жиры: *{plan['fat']} г*\n"
        f"🍞 Углеводы: *{plan['carbs']} г*\n\n"
        f"Выбери раздел в меню!",
        parse_mode="Markdown"
    )
    await state.clear()
    await callback.answer()


# ────────────────────────────────────────────────────
# Генерация рациона
# ────────────────────────────────────────────────────
@router.message(F.text == "🤖 Сгенерировать рацион")
async def ai_meal(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        cursor = await db.execute(
            "SELECT weight, height, age, gender, goal, activity_level FROM users WHERE telegram_id = ?",
            (message.from_user.id,)
        )
        user = await cursor.fetchone()

    if not user:
        return await message.answer("Сначала пройди настройку через 🚀 Начать")

    weight, height, age, gender, goal, activity = user
    activity = activity or "moderate"
    plan = calculate_plan(weight, height, age, gender, goal, activity)

    msg = await message.answer("🤖 Генерирую рацион... ⏳")

    # asyncio.to_thread — запускаем синхронную функцию в пуле потоков
    result = await asyncio.to_thread(generate_meal_with_ai, weight, goal, plan["calories"], 500)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="regenerate_meal")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="close_message")]
    ])
    await msg.edit_text(result, reply_markup=keyboard)


@router.callback_query(F.data == "regenerate_meal")
async def regenerate_meal(callback: types.CallbackQuery):
    async with aiosqlite.connect("database.db") as db:
        cursor = await db.execute(
            "SELECT weight, height, age, gender, goal, activity_level FROM users WHERE telegram_id = ?",
            (callback.from_user.id,)
        )
        user = await cursor.fetchone()

    if not user:
        await callback.answer("Сначала настрой профиль!", show_alert=True)
        return

    weight, height, age, gender, goal, activity = user
    activity = activity or "moderate"
    plan = calculate_plan(weight, height, age, gender, goal, activity)

    await callback.message.edit_text("🤖 Генерирую другой вариант... ⏳")
    result = await asyncio.to_thread(generate_meal_with_ai, weight, goal, plan["calories"], 500)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой вариант", callback_data="regenerate_meal")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="close_message")]
    ])
    await callback.message.edit_text(result, reply_markup=keyboard)
    await callback.answer()