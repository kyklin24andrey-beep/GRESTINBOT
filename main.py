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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Список моделей для перебора (Failover)
MODELS = [
    "https://router.huggingface.co/hf-inference/models/Yamer-AI/SDXL_Unstable_Diffusers",
    "https://router.huggingface.co/hf-inference/models/runwayml/stable-diffusion-v1-5"
]

HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
translator = GoogleTranslator(source='auto', target='en')

async def query_hf(url, prompt: str):
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
        "x-use-cache": "false"
    }
    payload = {"inputs": prompt}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=60) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    return "loading"
                else:
                    err = await response.text()
                    logger.error(f"Ошибка модели {url.split('/')[-1]}: {response.status} - {err}")
                    return "error"
        except Exception as e:
            logger.error(f"Сетевая ошибка на {url}: {e}")
            return "error"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎨 Бот с авто-переключением моделей готов! Пиши запрос.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    status_msg = await message.answer("🔄 Обработка запроса...")
    
    try:
        translated = translator.translate(message.text)
    except:
        translated = message.text

    # Цикл по всем моделям из списка
    for model_url in MODELS:
        model_name = model_url.split('/')[-1]
        await status_msg.edit_text(f"⌛ Пробую модель: `{model_name}`...", parse_mode="Markdown")
        
        # 2 попытки на каждую модель (на случай если она "спит")
        for attempt in range(2):
            result = await query_hf(model_url, translated)
            
            if result == "loading":
                await status_msg.edit_text(f"⏳ `{model_name}` загружается (попытка {attempt+1}/2)...", parse_mode="Markdown")
                await asyncio.sleep(20)
                continue
            
            if isinstance(result, bytes):
                photo = BufferedInputFile(result, filename="art.png")
                await message.answer_photo(photo, caption=f"✨ Модель: {model_name}\n🔤 Запрос: {translated}")
                await status_msg.delete()
                return
            
            # Если вернулась ошибка, выходим из цикла попыток и идем к следующей модели
            break
        
        logger.info(f"Модель {model_name} не сработала, перехожу к следующей...")

    await status_msg.edit_text("❌ Все доступные модели сейчас перегружены или недоступны. Попробуй позже.")

async def handle_health(request):
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

