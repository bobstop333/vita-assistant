import io
import asyncio
import logging
import aiosqlite
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.ai import analyze_food_text, analyze_food_photo

logger = logging.getLogger(__name__)

router = Router()
DB = "database.db"


class FoodForm(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    confirming = State()


def confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сохранить", callback_data="food_save"),
            InlineKeyboardButton(text="❌ Отмена",   callback_data="food_back_to_menu")
        ]
    ])


def cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="food_back_to_menu")]
    ])


def food_main_keyboard():
    """Клавиатура главного экрана дневника питания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Добавить текстом", callback_data="food_add_text")],
        [InlineKeyboardButton(text="📸 Добавить фото",   callback_data="food_add_photo")],
        [InlineKeyboardButton(text="📋 История за день", callback_data="food_history")],
    ])


# ──────────────────────────────────────────────────────
# Показать дневник питания (главный экран)
# ──────────────────────────────────────────────────────
async def show_food_menu(user_id: int, target_message: types.Message):
    from services.nutrition import calculate_plan

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT weight, height, age, gender, goal, activity_level FROM users WHERE telegram_id = ?",
            (user_id,)
        )
        user = await cursor.fetchone()

        if not user:
            try:
                await target_message.edit_text(
                    "⚠️ Сначала заполни профиль через *🚀 Начать*",
                    parse_mode="Markdown"
                )
            except Exception:
                await target_message.answer(
                    "⚠️ Сначала заполни профиль через *🚀 Начать*",
                    parse_mode="Markdown"
                )
            return

        weight, height, age, gender, goal, activity = user
        activity = activity or "moderate"
        plan = calculate_plan(weight, height, age, gender, goal, activity)
        target_cal = plan["calories"]

        cursor = await db.execute(
            "SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs) FROM meals "
            "WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')",
            (user_id,)
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

    try:
        await target_message.edit_text(text, parse_mode="Markdown", reply_markup=food_main_keyboard())
    except Exception:
        await target_message.answer(text, parse_mode="Markdown", reply_markup=food_main_keyboard())


# ──────────────────────────────────────────────────────
# История питания за день
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "food_history")
async def food_history(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            """SELECT description, calories, protein, fat, carbs,
                      strftime('%H:%M', timestamp, 'localtime')
               FROM meals
               WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')
               ORDER BY timestamp ASC""",
            (callback.from_user.id,)
        )
        meals = await cursor.fetchall()

    if not meals:
        await callback.message.edit_text(
            "📋 *История питания*\n\n"
            "Сегодня ты ещё ничего не добавил.\n"
            "Нажми «Добавить» чтобы записать приём пищи!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="food_back_to_menu")]
            ])
        )
        await callback.answer()
        return

    total_cal = sum(m[1] or 0 for m in meals)
    total_p   = sum(m[2] or 0 for m in meals)
    total_f   = sum(m[3] or 0 for m in meals)
    total_c   = sum(m[4] or 0 for m in meals)

    lines = ["📋 *История питания за сегодня*\n"]
    for name, cal, prot, fat, carbs, time in meals:
        lines.append(f"🕐 *{time}* — {name}\n   🔥 {cal} ккал | 🥩 {prot}г | 🥑 {fat}г | 🍞 {carbs}г")

    lines.append(
        f"\n📊 *Итого:*\n"
        f"🔥 {total_cal} ккал | 🥩 {total_p}г | 🥑 {total_f}г | 🍞 {total_c}г"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="food_back_to_menu")]
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()


# ──────────────────────────────────────────────────────
# Кнопка "Назад" — возврат в меню питания
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "food_back_to_menu")
async def food_back_to_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_food_menu(callback.from_user.id, callback.message)
    await callback.answer()


# ──────────────────────────────────────────────────────
# Добавить текстом
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "food_add_text")
async def food_start_text(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 Напиши что ты съел — в свободной форме.\n\n"
        "_Например: «тарелка гречки, куриная грудка 150г и стакан кефира»_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(FoodForm.waiting_text)
    await callback.answer()


@router.message(FoodForm.waiting_text)
async def food_receive_text(message: types.Message, state: FSMContext):
    msg = await message.answer("🔍 Анализирую... ⏳")

    # asyncio.to_thread — запускаем синхронную функцию в пуле потоков
    result = await asyncio.to_thread(analyze_food_text, message.text)

    if not result:
        await msg.edit_text(
            "😕 Не удалось распознать еду. Попробуй описать подробнее.\n"
            "Например: *«2 яйца вкрутую и тост с маслом»*",
            parse_mode="Markdown",
            reply_markup=cancel_keyboard()
        )
        return

    await state.update_data(food=result)
    text = (
        f"🍽 *{result['name']}*\n\n"
        f"🔥 Калории: *{result['calories']} ккал*\n"
        f"🥩 Белки: *{result['protein']} г*\n"
        f"🥑 Жиры: *{result['fat']} г*\n"
        f"🍞 Углеводы: *{result['carbs']} г*\n\n"
        f"Сохранить в дневник?"
    )
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=confirm_keyboard())
    await state.set_state(FoodForm.confirming)


# ──────────────────────────────────────────────────────
# Добавить фото
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "food_add_photo")
async def food_start_photo(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 Отправь фото блюда, и я распознаю его!\n\n"
        "_Постарайся сделать чёткое фото при хорошем освещении_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(FoodForm.waiting_photo)
    await callback.answer()


@router.message(FoodForm.waiting_photo, F.photo)
async def food_receive_photo(message: types.Message, state: FSMContext, bot):
    msg = await message.answer("🔍 Анализирую фото... ⏳")

    photo = message.photo[-1]
    logger.info(f"Photo received: file_id={photo.file_id}, size={photo.file_size}")
    file = await bot.get_file(photo.file_id)

    bio = io.BytesIO()
    await bot.download_file(file.file_path, bio)
    image_bytes = bio.getvalue()
    logger.info(f"Downloaded photo: {len(image_bytes)} bytes")

    # asyncio.to_thread — запускаем синхронную функцию в пуле потоков
    result = await asyncio.to_thread(analyze_food_photo, image_bytes)
    logger.info(f"Analysis result: {result}")

    if not result:
        await msg.edit_text(
            "😕 Не удалось распознать блюдо на фото.\n"
            "Попробуй сфотографировать чётче или добавь текстом!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 Добавить текстом", callback_data="food_add_text"),
                    InlineKeyboardButton(text="📸 Повторить фото",   callback_data="food_add_photo")
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="food_back_to_menu")]
            ])
        )
        await state.clear()
        return

    await state.update_data(food=result)
    text = (
        f"🍽 *{result['name']}*\n\n"
        f"🔥 Калории: *{result['calories']} ккал*\n"
        f"🥩 Белки: *{result['protein']} г*\n"
        f"🥑 Жиры: *{result['fat']} г*\n"
        f"🍞 Углеводы: *{result['carbs']} г*\n\n"
        f"Сохранить в дневник?"
    )
    await msg.edit_text(text, parse_mode="Markdown", reply_markup=confirm_keyboard())
    await state.set_state(FoodForm.confirming)


@router.message(FoodForm.waiting_photo)
async def food_wrong_input_photo(message: types.Message, state: FSMContext):
    await message.answer(
        "📸 Пожалуйста, отправь *фото* блюда, а не текст!\n"
        "Или нажми «🔙 Назад» чтобы вернуться.",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )


# ──────────────────────────────────────────────────────
# Подтверждение сохранения
# ──────────────────────────────────────────────────────
@router.callback_query(FoodForm.confirming, F.data == "food_save")
async def food_save(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    food = data["food"]

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO meals (telegram_id, description, calories, protein, fat, carbs) VALUES (?, ?, ?, ?, ?, ?)",
            (callback.from_user.id, food["name"], food["calories"], food["protein"], food["fat"], food["carbs"])
        )
        await db.commit()

    await state.clear()
    await callback.answer("Записано! 🥗")
    await show_food_menu(callback.from_user.id, callback.message)


@router.callback_query(FoodForm.confirming, F.data == "food_back_to_menu")
async def food_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_food_menu(callback.from_user.id, callback.message)
    await callback.answer()
