import os
import asyncio
import base64
import tempfile

from google import genai
from google.genai import types
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL")

SYSTEM_PROMPT = (
    "Siz O'zbek tilida gaplashadigan foydali AI assistantsiz. "
    "Foydalanuvchi bilan O'zbek tilida muloqot qiling. "
    "Javoblaringiz qisqa, aniq va tushunarli bo'lsin. "
    "Agar foydalanuvchi Notion vazifalari yoki Calendar haqida so'rasa, "
    "tegishli buyruqlarni (/addtask, /tasks, /today) taklif qiling."
)


async def handle_voice(message: Message, bot):
    """
    Gemini Live API (WebSocket) orqali:
    1. Ovozni yuklab olish
    2. Live session ochish — audio yuborish
    3. Audio javob olish
    4. Telegram ga yuborish
    """
    processing_msg = await message.answer("🎙️ Ovoz qabul qilindi, tahlil qilinmoqda...")

    try:
        # ── 1. Ovozli faylni yuklab olish ──
        voice = message.voice
        file = await bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            ogg_path = tmp.name

        with open(ogg_path, "rb") as f:
            audio_bytes = f.read()
        os.unlink(ogg_path)

        await processing_msg.edit_text("🤖 Gemini Live tahlil qilmoqda...")

        # ── 2. Gemini Live API — WebSocket session ──
        client = genai.Client(api_key=GEMINI_API_KEY)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=SYSTEM_PROMPT,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                )
            )
        )

        reply_audio = bytearray()
        reply_text = ""

        async with client.aio.live.connect(model=MODEL, config=config) as session:
            # Audio yuborish
            await session.send_realtime_input(
                audio=types.Blob(
                    mime_type="audio/ogg",
                    data=audio_bytes
                )
            )

            # Javobni olish
            async for response in session.receive():
                if response.data:
                    reply_audio.extend(response.data)
                if response.text:
                    reply_text += response.text
                if response.server_content and response.server_content.turn_complete:
                    break

        await processing_msg.edit_text("🔊 Javob tayyorlanmoqda...")

        # ── 3. Telegram ga yuborish ──
        await processing_msg.delete()

        if reply_text:
            await message.answer(f"🤖 <b>Gemini:</b> {reply_text}")

        if reply_audio:
            audio_file = BufferedInputFile(bytes(reply_audio), filename="response.ogg")
            await message.answer_voice(audio_file)
        else:
            await message.answer("❌ Audio javob olinmadi.")

    except Exception as e:
        await processing_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        raise e