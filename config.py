from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PROXY_URL = os.getenv("PROXY_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
