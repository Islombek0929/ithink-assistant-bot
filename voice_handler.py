import os
import asyncio
import base64
import tempfile
import wave
import struct

from google import genai
from google.genai import types
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.1-flash-live-preview"

SYSTEM_PROMPT = (
    "Siz O'zbek tilida gaplashadigan foydali AI assistantsiz. "
    "Foydalanuvchi bilan O'zbek tilida muloqot qiling. "
    "Javoblaringiz qisqa, aniq va tushunarli bo'lsin. "
    "Agar foydalanuvchi Notion vazifalari yoki Calendar haqida so'rasa, "
    "tegishli buyruqlarni (/addtask, /tasks, /today) taklif qiling."
)


def ogg_to_pcm(ogg_path: str) -> bytes:
    """OGG faylni PCM (16kHz, 16bit, mono) ga o'girish"""
    audio = AudioSegment.from_ogg(ogg_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return audio.raw_data


async def handle_voice(message: Message, bot):
    processing_msg = await message.answer("🎙️ Ovoz qabul qilindi, tahlil qilinmoqda...")

    try:
        # ── 1. Ovozli faylni yuklab olish ──
        voice = message.voice
        file = await bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await bot.download_file(file.file_path, tmp.name)
            ogg_path = tmp.name

        # ── 2. OGG → PCM convert ──
        await processing_msg.edit_text("🔄 Audio tayyorlanmoqda...")
        pcm_bytes = await asyncio.to_thread(ogg_to_pcm, ogg_path)
        os.unlink(ogg_path)

        await processing_msg.edit_text("🤖 Gemini Live tahlil qilmoqda...")

        # ── 3. Gemini Live API ──
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
            # PCM audio yuborish
            await session.send_realtime_input(
                audio=types.Blob(
                    mime_type="audio/pcm;rate=16000",
                    data=pcm_bytes
                )
            )

            # Javobni olish
            async for response in session.receive():
                if hasattr(response, 'data') and response.data:
                    reply_audio.extend(response.data)
                if hasattr(response, 'text') and response.text:
                    reply_text += response.text
                if (hasattr(response, 'server_content') and
                        response.server_content and
                        response.server_content.turn_complete):
                    break

        await processing_msg.delete()

        # ── 4. Javobni yuborish ──
        if reply_text:
            await message.answer(f"🤖 <b>Gemini:</b> {reply_text}")

        if reply_audio:
            # PCM → OGG ga o'girish (Telegram uchun)
            reply_pcm = bytes(reply_audio)
            reply_segment = AudioSegment(
                data=reply_pcm,
                sample_width=2,
                frame_rate=24000,
                channels=1
            )
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as out_tmp:
                reply_segment.export(out_tmp.name, format="ogg", codec="libopus")
                with open(out_tmp.name, "rb") as f:
                    ogg_out = f.read()
                os.unlink(out_tmp.name)

            audio_file = BufferedInputFile(ogg_out, filename="response.ogg")
            await message.answer_voice(audio_file)
        else:
            await message.answer("❌ Audio javob olinmadi.")

    except Exception as e:
        await processing_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        raise e