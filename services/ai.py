import json
import base64
import logging
import os
import requests as req

logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_VISION_MODELS = ["gemini-3.1-flash-lite", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]

_proxy_url = os.getenv("PROXY_URL", "")
PROXIES = {"http": _proxy_url, "https": _proxy_url} if _proxy_url else {}

def _gemini(prompt: str, max_tokens: int = 500, system: str = None) -> str | None:
    """Отправляет текстовый запрос в Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    
    contents = [{"parts": [{"text": prompt}]}]
    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens}
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    
    try:
        r = req.post(url, json=payload, proxies=PROXIES, timeout=60)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            logger.error(f"Gemini {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None


def _gemini_vision(image_bytes: bytes, prompt: str, max_tokens: int = 200) -> str | None:
    """Отправляет изображение + текст в Gemini API (vision)."""
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
                {"text": prompt}
            ]
        }],
        "generationConfig": {"maxOutputTokens": max_tokens}
    }
    
    for model in GEMINI_VISION_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
        try:
            r = req.post(url, json=payload, proxies=PROXIES, timeout=60)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                logger.info(f"Vision OK with {model}")
                return text
            else:
                logger.warning(f"Vision {model} failed: {r.status_code}")
        except Exception as e:
            logger.warning(f"Vision {model} error: {e}")
    
    return None


def _parse_json(raw: str):
    """Извлекает JSON из ответа, убирая markdown-блоки."""
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    raw = raw.strip()
    return json.loads(raw)


# ─── Генерация рациона ───
def generate_meal_with_ai(weight, goal, calories, budget):
    prompt = f"""Составь рацион на 1 день.
Вес: {weight} кг, Цель: {goal}, Калории: {calories}, Бюджет: {budget} руб/день.
Завтрак, обед, ужин. Дешёвые продукты, простые блюда, примерные калории. Кратко, с эмодзи."""
    return _gemini(
        prompt, max_tokens=600,
        system="Ты фитнес-тренер и нутрициолог."
    ) or "😕 Не удалось сгенерировать рацион. Попробуй позже."


# ─── ИИ-чат ───
def ask_ai(text: str) -> str:
    result = _gemini(
        text, max_tokens=300,
        system="Ты дружелюбный ИИ-ассистент VITA по ЗОЖ. Отвечай кратко, с эмодзи."
    )
    return result or "😕 Не удалось получить ответ. Попробуй позже."


# ─── Анализ еды по тексту ───
def analyze_food_text(text: str) -> dict:
    prompt = f'Определи КБЖУ для: "{text}". Ответь ТОЛЬКО валидным JSON без markdown: {{"name":"название","calories":0,"protein":0,"fat":0,"carbs":0}}'
    try:
        raw = _gemini(
            prompt, max_tokens=150,
            system="Ты точный нутрициолог. Отвечаешь ТОЛЬКО JSON, без пояснений."
        )
        return _parse_json(raw)
    except Exception as e:
        logger.error(f"analyze_food_text error: {e}")
        return None


# ─── Анализ еды по фото ───
def analyze_food_photo(image_bytes: bytes) -> dict:
    prompt = """На фото еда. Определи что это и верни ТОЛЬКО валидный JSON без markdown:
{"name":"название блюда","calories":число,"protein":граммы,"fat":граммы,"carbs":граммы}
Числа — целые. Если несколько блюд — суммируй."""
    try:
        raw = _gemini_vision(image_bytes, prompt, max_tokens=200)
        logger.info(f"[VISION] raw: {raw[:100] if raw else 'None'}")
        return _parse_json(raw)
    except Exception as e:
        logger.error(f"analyze_food_photo error: {e}")
        return None


# ─── Генерация тренировки ───
def generate_workout(goal: str, location: str) -> str:
    prompt = f"""Составь тренировку на сегодня.
Цель: {goal}, Место: {location}.
Разминка / Основная часть (4-5 упражнений с подходами×повт.) / Заминка.
Кратко, с эмодзи, укажи время."""
    return _gemini(
        prompt, max_tokens=500,
        system="Ты профессиональный фитнес-тренер."
    ) or "😕 Не удалось сгенерировать тренировку. Попробуй позже."