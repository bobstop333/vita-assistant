import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from config import BOT_TOKEN, PROXY_URL
from handlers import start, onboarding, menu, food, workout, progress
from db import init_db

session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

async def main():
    await init_db()

    dp.include_router(start.router)
    dp.include_router(onboarding.router)
    dp.include_router(food.router)
    dp.include_router(workout.router)
    dp.include_router(progress.router)
    # menu.router подключаем последним, так как там есть общий обработчик текста (ai_handler)
    dp.include_router(menu.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())