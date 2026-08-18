from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# Mini App URL (GitHub Pages)
MINI_APP_URL = "https://bobstop333.github.io/vita-assistant/webapp/miniapp/"

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Начать"), KeyboardButton(text="🤖 Сгенерировать рацион")],
            [KeyboardButton(text="🥗 Расчет рациона"), KeyboardButton(text="💧 Вода")],
            [KeyboardButton(text="🏋️ Тренировки"), KeyboardButton(text="📸 Мой прогресс")],
            [KeyboardButton(text="📊 Мой дашборд", web_app=WebAppInfo(url=MINI_APP_URL))],
        ],
        resize_keyboard=True
    )