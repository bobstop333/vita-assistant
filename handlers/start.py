from aiogram import Router, types
from aiogram.filters import CommandStart
from keyboards.main_menu import main_kb

router = Router()

@router.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "Привет 👋\nВыбери действие:",
        reply_markup=main_kb()
    )