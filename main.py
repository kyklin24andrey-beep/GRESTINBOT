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

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

API_URL = "https://router.huggingface.co/hf-inference/models/nroggendorff/unstable-diffusion"
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")

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

    logger.info(f">>> Отправка запроса к HF. Промпт: {prompt}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, headers=headers, json=payload, timeout=90) as response:
                content_type = response.headers.get('Content-Type', '')
                
                if response.status == 200:
                    logger.info("<<< Успешный ответ от API (200 OK)")
                    return await response.read()
                
                elif response.status == 503:
                    logger.warning("<<< Модель загружается (503 Service Unavailable)")
                    return "loading"
                
                else:
                    err_text = await response.text()
                    logger.error(f"<<< Ошибка API {response.status}: {err_text}")
                    return f"error_{response.status}_{err_text}"
                    
        except Exception as e:
            logger.error(f"!!! Ошибка сети/соединения: {str(e)}")
            return f"exception_{str(e)}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎨 Бот запущен! Пиши запрос на любом языке.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_input = message.text
    logger.info(f"Сообщение от пользователя {message.from_user.id}: {user_input}")
    
    status_msg = await message.answer("🔄 Обработка...")

    try:
        translated_prompt = translator.translate(user_input)
        logger.info(f"Перевод: {translated_prompt}")
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        translated_prompt = user_input

    await status_msg.edit_text(f"⌛ Генерирую по запросу: `{translated_prompt}`", parse_mode="Markdown")
    
    for i in range(3):
        result = await query_hf(translated_prompt)
        
        if result == "loading":
            await status_msg.edit_text(f"⏳ Модель просыпается... Попытка {i+1}/3")
            await asyncio.sleep(25)
            continue
        
        if isinstance(result, bytes):
            photo = BufferedInputFile(result, filename="art.png")
            await message.answer_photo(
                photo, 
                caption=f"✨ Готово!\n🔤 Промпт: {translated_prompt}"
            )
            await status_msg.delete()
            return
        
        # Если пришла ошибка
        error_info = str(result)
        await status_msg.edit_text(f"❌ Ошибка при генерации.\nКод: `{error_info[:100]}`", parse_mode="Markdown")
        return

    await status_msg.edit_text("❌ Модель не успела проснуться. Попробуй еще раз через минуту.")

async def handle_health(request):
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    asyncio.create_task(site.start())

    logger.info("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
