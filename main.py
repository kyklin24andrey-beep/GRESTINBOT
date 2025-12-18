import asyncio
import os
import aiohttp
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from dotenv import load_dotenv
from aiohttp import web
from deep_translator import GoogleTranslator

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# ОБНОВЛЕННЫЙ URL (Новый роутер Hugging Face)
API_URL = "https://router.huggingface.co/hf-inference/models/nroggendorff/unstable-diffusion"

# Токены (очистка от лишних пробелов)
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
translator = GoogleTranslator(source='auto', target='en')

async def query_hf(prompt: str):
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
        "x-use-cache": "false"
    }
    payload = {"inputs": prompt}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, headers=headers, json=payload, timeout=120) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    return "loading"
                else:
                    err = await response.text()
                    logger.error(f"API Error {response.status}: {err}")
                    return None
        except Exception as e:
            logger.error(f"Network error: {e}")
            return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎨 Привет! Напиши мне, что нарисовать. Я понимаю русский язык!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    status_msg = await message.answer("🔄 Перевожу запрос...")
    
    try:
        # Перевод на английский
        translated = translator.translate(message.text)
        logger.info(f"User: {message.text} | Translated: {translated}")
    except Exception as e:
        logger.error(f"Translation error: {e}")
        translated = message.text

    await status_msg.edit_text(f"⌛ Генерирую по запросу: `{translated}`", parse_mode="Markdown")
    
    # Попытки генерации (если модель "спит")
    for i in range(3):
        result = await query_hf(translated)
        
        if result == "loading":
            await status_msg.edit_text(f"⏳ Модель загружается на сервере... Попытка {i+1}/3")
            await asyncio.sleep(25)
            continue
        
        if isinstance(result, bytes):
            photo = BufferedInputFile(result, filename="art.png")
            await message.answer_photo(photo, caption=f"✨ Готово!\n🔤 Запрос: {translated}")
            await status_msg.delete()
            return
        break

    await status_msg.edit_text("❌ Не удалось получить ответ от нейросети. Попробуй позже.")

# Веб-сервер для Health Check на Render
async def handle_health(request):
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    
    logger.info("Бот запущен через новый роутер!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
