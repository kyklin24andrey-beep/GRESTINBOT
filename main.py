import asyncio
import os
import aiohttp
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiohttp import web
from deep_translator import GoogleTranslator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Словари для хранения настроек пользователей
user_settings = {} # {user_id: {'engine': 'hf', 'model': 'sdxl_y'}}

# Набор моделей Hugging Face
HF_MODELS = {
    "sdxl_y": "Yamer-AI/SDXL_Unstable_Diffusers_Y",
    "unstable_v2": "stablediffusionapi/unstable-diffusion-v2",
    "unstable_v15": "AnnieL/unstable-diffusion-v1-5"
}

HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
translator = GoogleTranslator(source='auto', target='en')

# --- КЛАВИАТУРЫ ---
def get_settings_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Источник: Hugging Face 🤖", callback_data="set_engine_hf")],
        [InlineKeyboardButton(text="Источник: Pollinations 🐝", callback_data="set_engine_poll")],
        [InlineKeyboardButton(text="Выбрать модель HF ⚙️", callback_data="show_models")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_models_keyboard():
    buttons = [
        [InlineKeyboardButton(text="SDXL Unstable Y", callback_data="model_sdxl_y")],
        [InlineKeyboardButton(text="Unstable v2", callback_data="model_unstable_v2")],
        [InlineKeyboardButton(text="Unstable v1.5", callback_data="model_unstable_v15")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_settings")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ФУНКЦИИ API ---
async def get_from_pollinations(prompt: str):
    seed = random.randint(0, 999999)
    url = f"https://image.pollinations.ai/prompt/{prompt}?nologo=true&seed={seed}&width=1024&height=1024"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=60) as response:
                if response.status == 200: return await response.read()
        except: pass
    return None

async def query_hf(model_path, prompt: str):
    url = f"https://router.huggingface.co/hf-inference/models/{model_path}"
    headers = {"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"negative_prompt": "blurry, distorted", "guidance_scale": 7.5}}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=90) as response:
                if response.status == 200: return await response.read()
                if response.status == 503: return "loading"
        except: pass
    return None

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_settings[message.from_user.id] = {'engine': 'hf', 'model': 'sdxl_y'}
    await message.answer("🔞 Бот готов к генерации без цензуры!\nПо умолчанию: Hugging Face (SDXL Unstable).", 
                         reply_markup=get_settings_keyboard())

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    await message.answer("⚙️ Настройки ресурсов:", reply_markup=get_settings_keyboard())

@dp.callback_query(F.data.startswith("set_engine_"))
async def set_engine(callback: types.CallbackQuery):
    engine = callback.data.split("_")[-1]
    uid = callback.from_user.id
    if uid not in user_settings: user_settings[uid] = {'engine': 'hf', 'model': 'sdxl_y'}
    user_settings[uid]['engine'] = engine
    await callback.answer(f"Выбран источник: {engine.upper()}")
    await callback.message.edit_text(f"✅ Текущий источник: {'Hugging Face' if engine == 'hf' else 'Pollinations'}", 
                                     reply_markup=get_settings_keyboard())

@dp.callback_query(F.data == "show_models")
async def show_models(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите модель для Hugging Face:", reply_markup=get_models_keyboard())

@dp.callback_query(F.data.startswith("model_"))
async def set_model(callback: types.CallbackQuery):
    model_key = callback.data.replace("model_", "")
    uid = callback.from_user.id
    if uid not in user_settings: user_settings[uid] = {'engine': 'hf', 'model': 'sdxl_y'}
    user_settings[uid]['model'] = model_key
    user_settings[uid]['engine'] = 'hf' # Авто-переключение на HF при выборе модели
    await callback.answer(f"Выбрана модель: {model_key}")
    await callback.message.edit_text(f"✅ Модель HF: {HF_MODELS[model_key]}", reply_markup=get_settings_keyboard())

@dp.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: types.CallbackQuery):
    await callback.message.edit_text("⚙️ Настройки ресурсов:", reply_markup=get_settings_keyboard())

@dp.message(F.text)
async def handle_text(message: types.Message):
    uid = message.from_user.id
    # Загружаем настройки или ставим дефолт
    settings = user_settings.get(uid, {'engine': 'hf', 'model': 'sdxl_y'})
    
    status_msg = await message.answer("🔄 Обработка...")
    try:
        translated = translator.translate(message.text)
    except:
        translated = message.text

    result = None
    engine_name = ""

    if settings['engine'] == 'hf':
        model_path = HF_MODELS[settings['model']]
        engine_name = f"Hugging Face ({settings['model']})"
        await status_msg.edit_text(f"⌛ Генерирую через {engine_name}...")
        result = await query_hf(model_path, translated)
        if result == "loading":
            await status_msg.edit_text("⏳ Модель спит, жду 20 сек...")
            await asyncio.sleep(20)
            result = await query_hf(model_path, translated)
    else:
        engine_name = "Pollinations AI"
        await status_msg.edit_text(f"⌛ Генерирую через {engine_name}...")
        result = await get_from_pollinations(translated)

    if isinstance(result, bytes):
        photo = BufferedInputFile(result, filename="art.png")
        await message.answer_photo(photo, caption=f"✅ Источник: {engine_name}\n📝 Запрос: {translated}")
        await status_msg.delete()
    else:
        await status_msg.edit_text("❌ Ошибка генерации. Попробуй сменить модель или ресурс в /settings")

async def handle_health(request): return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080))).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
