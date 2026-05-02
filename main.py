import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv

from voice_handler import handle_voice
from notion_handler import (
    add_task, list_tasks, complete_task,
    send_overdue_tasks
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ─────────────────────────────────────────
# 🎙️ OVOZLI XABAR — Whisper + Gemini + TTS
# ─────────────────────────────────────────
@dp.message(F.voice)
async def voice_message_handler(message: Message):
    await handle_voice(message, bot)


# ─────────────────────────────────────────
# 📋 NOTION — Vazifa qo'shish
# /addtask [ish|shaxsiy] Vazifa nomi
# ─────────────────────────────────────────
@dp.message(Command("addtask"))
async def add_task_handler(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "📝 Format:\n"
            "/addtask ish Vazifa nomi\n"
            "/addtask shaxsiy Vazifa nomi\n\n"
            "Misol: /addtask ish IT Infra variant tahlili"
        )
        return

    db_type = args[1].lower()
    task_name = args[2]

    if db_type not in ["ish", "shaxsiy"]:
        await message.answer("❌ Faqat 'ish' yoki 'shaxsiy' deb yozing!")
        return

    await message.answer("⏳ Qo'shilmoqda...")
    result = await add_task(task_name, db_type)

    if result:
        await message.answer(
            f"✅ Vazifa qo'shildi!\n\n💼 *{task_name}*\n📂 {db_type.capitalize()} vazifalar",
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")


# ─────────────────────────────────────────
# 📋 NOTION — Vazifalarni ko'rish
# /tasks [ish|shaxsiy] [bugun|ertaga|hammasi]
# ─────────────────────────────────────────
@dp.message(Command("tasks"))
async def list_tasks_handler(message: Message):
    args = message.text.split()
    db_type = args[1].lower() if len(args) > 1 else "ish"
    filter_type = args[2].lower() if len(args) > 2 else "bugun"

    if db_type not in ["ish", "shaxsiy"]:
        db_type = "ish"

    await message.answer("⏳ Notion'dan yuklanmoqda...")
    tasks_text = await list_tasks(db_type, filter_type)
    await message.answer(tasks_text, parse_mode="Markdown")


# ─────────────────────────────────────────
# ✅ NOTION — Vazifani bajarildi qilish
# /done vazifa_nomi
# ─────────────────────────────────────────
@dp.message(Command("done"))
async def done_task_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("✅ Format: /done Vazifa nomi (yoki qismi)")
        return

    task_name = args[1]
    await message.answer("⏳ Yangilanmoqda...")
    result = await complete_task(task_name)

    if result:
        await message.answer(f"✅ Bajarildi deb belgilandi!\n\n*{result}*", parse_mode="Markdown")
    else:
        await message.answer("❌ Vazifa topilmadi. Nomni tekshiring.")


# ─────────────────────────────────────────
# 📊 Bugungi hisobot
# ─────────────────────────────────────────
@dp.message(Command("today"))
async def today_handler(message: Message):
    await message.answer("📊 Bugungi vazifalar yuklanmoqda...")
    ish = await list_tasks("ish", "bugun")
    shaxsiy = await list_tasks("shaxsiy", "bugun")
    await message.answer(
        f"💼 *ISH:*\n{ish}\n\n🌿 *SHAXSIY:*\n{shaxsiy}",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────
# ❓ START va HELP
# ─────────────────────────────────────────
@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "👋 Salom! Men sizning shaxsiy AI assistantingizman.\n\n"
        "🎙️ *Ovozli xabar* yuboring — Gemini AI O'zbek tilida javob beradi\n\n"
        "📋 *Notion buyruqlari:*\n"
        "/addtask ish [vazifa] — Ish vazifasi qo'shish\n"
        "/addtask shaxsiy [vazifa] — Shaxsiy vazifa qo'shish\n"
        "/tasks ish bugun — Bugungi ish vazifalari\n"
        "/tasks shaxsiy hammasi — Barcha shaxsiy vazifalar\n"
        "/done [vazifa nomi] — Vazifani bajarildi qilish\n"
        "/today — Bugungi to'liq hisobot\n"
        "/help — Barcha buyruqlar",
        parse_mode="Markdown"
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📖 *Barcha buyruqlar:*\n\n"
        "🎙️ *Ovoz:*\n"
        "• Ovozli xabar yuboring — Gemini AI javob beradi\n\n"
        "📋 *Notion:*\n"
        "• /addtask ish [nom] — Ish vazifasi qo'shish\n"
        "• /addtask shaxsiy [nom] — Shaxsiy vazifa qo'shish\n"
        "• /tasks ish bugun — Bugungi ish vazifalari\n"
        "• /tasks ish ertaga — Ertangi ish vazifalari\n"
        "• /tasks shaxsiy hammasi — Barcha shaxsiy vazifalar\n"
        "• /done [vazifa nomi] — Bajarildi deb belgilash\n"
        "• /today — Bugungi to'liq hisobot\n\n"
        "⚙️ *Boshqa:*\n"
        "• /start — Boshlash\n"
        "• /help — Yordam",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────
# ⏰ SCHEDULER — Har kuni ertalab 9:00 da
# ─────────────────────────────────────────
async def daily_scheduler():
    import datetime
    CHAT_ID = os.getenv("YOUR_CHAT_ID")

    while True:
        now = datetime.datetime.now()
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += datetime.timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        try:
            ish = await list_tasks("ish", "bugun")
            shaxsiy = await list_tasks("shaxsiy", "bugun")
            overdue = await send_overdue_tasks()

            text = "☀️ *Xayrli tong! Bugungi reja:*\n\n"
            text += f"💼 *ISH:*\n{ish}\n\n"
            text += f"🌿 *SHAXSIY:*\n{shaxsiy}"
            if overdue:
                text += f"\n\n⚠️ *Muddati o'tgan:*\n{overdue}"

            await bot.send_message(CHAT_ID, text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Scheduler xatosi: {e}")


# ─────────────────────────────────────────
# 🚀 BOT ISHGA TUSHIRISH
# ─────────────────────────────────────────
async def main():
    logger.info("Bot ishga tushmoqda... (Gemini 2.0 Flash)")
    await asyncio.gather(
        dp.start_polling(bot),
        daily_scheduler()
    )

if __name__ == "__main__":
    asyncio.run(main())
