import io
import aiosqlite
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

router = Router()
DB = "database.db"


class ProgressForm(StatesGroup):
    waiting_weight = State()


def progress_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚖️ Записать текущий вес", callback_data="progress_add_weight")],
        [InlineKeyboardButton(text="📈 График веса",          callback_data="progress_chart")],
        [InlineKeyboardButton(text="🔙 Назад",                callback_data="close_message")]
    ])


def progress_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="progress_cancel_fsm")]
    ])


@router.callback_query(F.data == "progress_cancel_fsm")
async def progress_cancel_fsm(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.", reply_markup=progress_keyboard())
    await callback.answer()


@router.message(F.text == "📸 Мой прогресс")
async def progress_handler(message: types.Message):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT weight, goal FROM users WHERE telegram_id = ?",
            (message.from_user.id,)
        )
        user = await cursor.fetchone()

        if not user:
            await message.answer("⚠️ Сначала заполни профиль через *🚀 Начать*", parse_mode="Markdown")
            return

        start_weight, goal = user

        cursor = await db.execute(
            "SELECT weight, date FROM weight_logs WHERE telegram_id = ? ORDER BY date DESC LIMIT 7",
            (message.from_user.id,)
        )
        logs = await cursor.fetchall()

        # КБЖУ за сегодня
        cursor = await db.execute(
            "SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs) FROM meals "
            "WHERE telegram_id = ? AND date(timestamp) = date('now', 'localtime')",
            (message.from_user.id,)
        )
        today = await cursor.fetchone()

    text = f"📈 *Твой прогресс*\n\n"
    text += f"🎯 Цель: _{goal}_\n"
    text += f"🏁 Стартовый вес: *{start_weight} кг*\n\n"

    if logs:
        current_weight = logs[0][0]
        diff = round(current_weight - start_weight, 1)
        diff_str = f"+{diff}" if diff > 0 else f"{diff}"
        diff_emoji = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
        text += f"⚖️ Текущий вес: *{current_weight} кг* {diff_emoji} ({diff_str} кг от старта)\n\n"
        text += "📅 *Последние записи:*\n"
        for w, d in logs:
            text += f"• {d}: {w} кг\n"
    else:
        text += "У тебя пока нет записей веса.\nНажми кнопку ниже, чтобы начать отслеживание!\n"

    # Сегодняшнее питание
    if today and today[0]:
        text += f"\n🍽 *Сегодня съедено:*\n"
        text += f"🔥 {today[0] or 0} ккал | 🥩 {today[1] or 0}г | 🥑 {today[2] or 0}г | 🍞 {today[3] or 0}г"

    await message.answer(text, parse_mode="Markdown", reply_markup=progress_keyboard())


# ──────────────────────────────────────────────────────
# График веса
# ──────────────────────────────────────────────────────
def _build_weight_chart(dates: list, weights: list) -> bytes:
    """Строит PNG-график динамики веса (синхронно)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from datetime import datetime

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#16213e")

    # Парсим даты
    dt_dates = [datetime.strptime(d, "%Y-%m-%d") for d in dates]

    ax.plot(dt_dates, weights, color="#e94560", linewidth=2.5, marker="o",
            markersize=6, markerfacecolor="#f5a623", markeredgecolor="#e94560")

    # Заливка под линией
    ax.fill_between(dt_dates, weights, alpha=0.15, color="#e94560")

    # Стиль
    ax.set_title("📈 Динамика веса", color="white", fontsize=14, pad=12)
    ax.set_ylabel("Вес (кг)", color="#aaaaaa", fontsize=11)
    ax.tick_params(colors="#aaaaaa", labelsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.xticks(rotation=30, ha="right")

    ax.spines["bottom"].set_color("#444")
    ax.spines["left"].set_color("#444")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color="#333", linestyle="--", alpha=0.5)

    # Подписи значений
    for dt, w in zip(dt_dates, weights):
        ax.annotate(f"{w}", (dt, w), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color="white")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


@router.callback_query(F.data == "progress_chart")
async def show_weight_chart(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT weight, date FROM weight_logs WHERE telegram_id = ? ORDER BY date ASC LIMIT 30",
            (callback.from_user.id,)
        )
        logs = await cursor.fetchall()

    if len(logs) < 2:
        await callback.answer("Нужно минимум 2 записи веса для графика!", show_alert=True)
        return

    weights = [row[0] for row in logs]
    dates   = [row[1] for row in logs]

    await callback.message.answer("📊 Строю график...")

    # Строим в отдельном потоке (matplotlib синхронный)
    png_bytes = await asyncio.to_thread(_build_weight_chart, dates, weights)

    photo_file = BufferedInputFile(png_bytes, filename="weight_chart.png")
    await callback.message.answer_photo(
        photo=photo_file,
        caption=f"📈 *График веса* за {len(logs)} дней\n"
                f"📉 Мин: {min(weights)} кг | 📈 Макс: {max(weights)} кг",
        parse_mode="Markdown"
    )
    await callback.answer()


# ──────────────────────────────────────────────────────
# Добавить вес
# ──────────────────────────────────────────────────────
@router.callback_query(F.data == "progress_add_weight")
async def add_weight_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "⚖️ Введи текущий вес в кг (например: *75.5*):",
        parse_mode="Markdown",
        reply_markup=progress_cancel_keyboard()
    )
    await state.set_state(ProgressForm.waiting_weight)
    await callback.answer()


@router.message(ProgressForm.waiting_weight)
async def add_weight_finish(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        assert 20 <= weight <= 400
    except Exception:
        await message.answer("❌ Введи корректный вес (например: 75.5)")
        return

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO weight_logs (telegram_id, weight) VALUES (?, ?)",
            (message.from_user.id, weight)
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ Вес *{weight} кг* записан!\n\n"
        f"Смотри динамику в разделе «📸 Мой прогресс» → «📈 График веса».",
        parse_mode="Markdown"
    )
