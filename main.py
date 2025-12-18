import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from dotenv import load_dotenv
from aiohttp import web

# Загружаем переменные из .env (если файл есть)
load_dotenv()

# Настройки (Берутся из Environment Variables на Render)
API_URL = "https://router.huggingface.co/hf-inference/models/nroggendorff/unstable-diffusion"
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def query_hf(prompt: str):
    """Отправка запроса к API Hugging Face"""
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
        "x-use-cache": "false"
    }
    payload = {"inputs": prompt}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(API_URL, headers=headers, json=payload, timeout=90) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    return "loading"
                else:
                    err_text = await response.text()
                    print(f"API Error {response.status}: {err_text}")
                    return None
        except Exception as e:
            print(f"Network error: {e}")
            return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🎨 Привет! Напиши, что мне нарисовать (на английском).\n\n"
                         "Например: `cyberpunk city landscape, high detail`")

@dp.message(F.text)
async def handle_text(message: types.Message):
    status_msg = await message.answer("⌛ Начинаю генерацию... Это может занять до минуты.")
    
    # Пытаемся получить картинку (3 попытки если модель спит)
    for i in range(3):
        result = await query_hf(message.text)
        
        if result == "loading":
            await status_msg.edit_text(f"⏳ Модель загружается на сервере... Пробую еще раз ({i+1}/3)")
            await asyncio.sleep(25) # Модели нужно время проснуться
            continue
        
        if isinstance(result, bytes):
            photo = BufferedInputFile(result, filename="gen_image.png")
            await message.answer_photo(photo, caption=f"✨ Готово по запросу: {message.text}")
            await status_msg.delete()
            return
        else:
            break

    await status_msg.edit_text("❌ Не удалось сгенерировать. Попробуй позже или измени запрос.")

# --- Секция для Render (Web Server) ---
async def handle_health_check(request):
    return web.Response(text="Bot is alive", status=200)

async def main():
    # Создаем и запускаем веб-сервер для Health Check на Render
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    print(f"Starting web server on port {port}")
    asyncio.create_task(site.start())

    # Запускаем бота
    print("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")