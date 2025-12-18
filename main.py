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

# НОВАЯ МОДЕЛЬ (SDXL Unstable Diffusers) через роутер
API_URL = "https://router.huggingface.co/hf-inference/models/stablediffusionapi/sdxl-unstable-diffusers-y"

# Токены
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
    # Для SDXL можно добавить параметры качества
    payload = {
        "inputs": prompt,
        "parameters": {
            "negative_prompt": "blurry, bad quality, distorted",
            "guidance_scale": 7.5
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # Увеличили таймаут до 150 секунд для тяжелой модели
            async with session.post(API_URL, headers=headers, json=payload, timeout=150) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    return "loading"
                else:
                    err = await response.text()
                    logger.error(f"API Error {response.status}: {err}")
                    return f"error_{response.status}"
        except Exception as e:
            logger.error(f"Network error: {e}")
            return "network_error"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎨 Бот обновлен до SDXL! Пиши запрос (можно на русском), и я создам шедевр.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    status_msg = await message.answer("🔄 Перевожу и запускаю SDXL...")
    
    try:
        translated = translator.translate(message.text)
        logger.info(f"Запрос: {message.text} -> {translated}")
    except:
        translated = message.text

    await status_msg.edit_text(f"⌛ Генерирую через SDXL: `{translated}`", parse_mode="Markdown")
    
    # Пытаемся 3 раза (модели SDXL нужно время на прогрев)
    for i in range(3):
        result = await query_hf(translated)
        
        if result == "loading":
            await status_msg.edit_text(f"⏳ Тяжелая модель SDXL загружается... Попытка {i+1}/3")
            await asyncio.sleep(30)
            continue
        
        if isinstance(result, bytes):
            photo = BufferedInputFile(result, filename="sdxl_art.png")
            await message.answer_photo(photo, caption=f"✨ SDXL Модель\n🔤 Промпт: {translated}")
            await status_msg.delete()
            return
        
        # Если пришла ошибка API
        await status_msg.edit_text(f"❌ Ошибка API: `{result}`. Попробуй еще раз через минуту.")
        return

    await status_msg.edit_text("❌ Модель не ответила вовремя. Попробуй отправить запрос еще раз.")

# Health Check для Render
async def handle_health(request):
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    
    logger.info("Бот на базе SDXL запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
