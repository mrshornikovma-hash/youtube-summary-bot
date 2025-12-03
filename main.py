import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
import yt_dlp
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 1. Загружаем конфиги
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# 2. Инициализация
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)

# Настройка yt-dlp (качаем только аудио, самый быстрый формат)
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}],
    'outtmpl': 'downloads/%(id)s.%(ext)s',
    'quiet': True
}

async def download_audio(url: str):
    """Скачивает аудио с YouTube и возвращает путь к файлу"""
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        return f"downloads/{info['id']}.mp3"

async def get_summary(text: str):
    """Отправляет транскрипцию в GPT для суммаризации"""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты бизнес-ассистент. Твоя задача — сделать структурированное саммари текста. Выдели: 1. Главную тему. 2. Ключевые тезисы (буллитами). 3. Вывод."},
            {"role": "user", "content": f"Сделай саммари этого текста:\n\n{text[:15000]}"} # Обрезаем, чтобы не перегрузить контекст
        ]
    )
    return response.choices[0].message.content

# --- Handlers ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Пришли мне ссылку на YouTube видео, и я сделаю конспект.")

@dp.message(F.text.contains("youtube.com") | F.text.contains("youtu.be"))
async def process_youtube_link(message: types.Message):
    status_msg = await message.answer("⏳ **Этап 1/3:** Скачиваю аудиодорожку...")
    
    try:
        # 1. Скачивание
        audio_path = await download_audio(message.text)
        
        # 2. Транскрибация (Whisper)
        await status_msg.edit_text("👂 **Этап 2/3:** Превращаю звук в текст (Whisper)...")
        with open(audio_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        
        # 3. Саммаризация (GPT)
        await status_msg.edit_text("🧠 **Этап 3/3:** Анализирую смысл...")
        summary = await get_summary(transcription.text)
        
        # Результат
        await status_msg.delete()
        await message.answer(f"📝 **Краткое содержание:**\n\n{summary}", parse_mode="Markdown")
        
        # Уборка (удаляем файл)
        os.remove(audio_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")

# --- Main ---

async def main():
    bot = Bot(token=TOKEN)
    logging.basicConfig(level=logging.INFO)
    print("Agent Py is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())