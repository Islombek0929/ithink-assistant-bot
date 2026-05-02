import os
import tempfile
import asyncio
import base64

from google import genai
from google.genai import types
from aiogram.types import Message, BufferedInputFile
from dotenv import load_dotenv

load_dotenv()

# google-genai==1.74.0 — yangi Client sintaksisi
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.0-flash-live-preview"

SYSTEM_PROMPT = (
    "Siz O'zbek tilida gaplashadigan foydali AI assistantsiz. "
    "Foydalanuvchi bilan O'zbek tilida muloqot qiling. "
    "Javoblaringiz qisqa, aniq va tushunarli bo'lsin. "
    "Agar foydalanuvchi Notion vazifalari yoki Calendar haqida so'rasa, "
    "tegishli buyruqlarni (/addtask, /tasks, /today) taklif qiling."
)


async def handle_voice(message: Message, bot):
    """
    1. Telegram'dan ovozli xabarni yuklab olish
    2. Gemini STT + LLM — ovozdan matn va javob
    3. Gemini TTS — javobni ovozga o'girish
    4. Telegram'ga ovozli javob yuborish
    """
    processing_msg = await message.answer("🎙️ Ovoz qabul qilindi, tahlil qilinmoqda...")

    try:
        # ── 1. Ovozli faylni yuklab olish ──
        voice = message.voice
        file = await bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_ogg:
            await bot.download_file(file.file_path, tmp_ogg.name)
            ogg_path = tmp_ogg.name

        with open(ogg_path, "rb") as f:
            audio_bytes_raw = f.read()
        audio_b64 = base64.b64encode(audio_bytes_raw).decode("utf-8")
        os.unlink(ogg_path)

        # ── 2. Gemini STT + LLM ──
        await processing_msg.edit_text("🤖 Gemini tahlil qilmoqda...")

        stt_response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="audio/ogg",
                                data=audio_b64
                            )
                        ),
                        types.Part(
                            text=(
                                "Bu ovozli xabarni O'zbek tilida tinglab, "
                                "avval [MATN]: deb foydalanuvchi nima deganini yoz, "
                                "keyin [JAVOB]: deb O'zbek tilida qisqa javob ber."
                            )
                        )
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
            )
        )

        full_text = stt_response.text or ""

        # MATN va JAVOB ni ajratib olish
        if "[MATN]:" in full_text and "[JAVOB]:" in full_text:
            parts = full_text.split("[JAVOB]:")
            user_text = parts[0].replace("[MATN]:", "").strip()
            reply_text = parts[1].strip()
        else:
            reply_text = full_text.strip()
            user_text = "Ovozli xabar"

        if not reply_text:
            await processing_msg.edit_text("❌ Javob olinmadi. Qayta urinib ko'ring.")
            return

        # ── 3. Gemini TTS ──
        await processing_msg.edit_text("🔊 Ovoz tayyorlanmoqda...")

        tts_response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=reply_text)]
                )
            ],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name="Aoede"
                        )
                    )
                )
            )
        )

        # Audio bytes olish
        tts_audio_bytes = tts_response.candidates[0].content.parts[0].inline_data.data

        # ── 4. Telegram'ga yuborish ──
        await processing_msg.delete()

        await message.answer(
            f"🎙️ <b>Siz:</b> {user_text}\n\n"
            f"🤖 <b>Gemini:</b> {reply_text}"
        )

        audio_input = BufferedInputFile(tts_audio_bytes, filename="response.wav")
        await message.answer_voice(audio_input)

    except Exception as e:
        await processing_msg.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        raise e