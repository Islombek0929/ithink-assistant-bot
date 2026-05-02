import asyncio
import logging
import os
import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from voice_handler import handle_voice
from notion_handler import add_task, list_tasks, complete_task, send_overdue_tasks

load_dotenv(dotenv_path='env.example')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("YOUR_CHAT_ID"))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ─────────────────────────────────────────
# 🔒 FAQAT OWNER — boshqa hech kim kirolmaydi
# ─────────────────────────────────────────
@dp.message.outer_middleware()
async def owner_only_middleware(handler, message: Message, data: dict):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Sizda bu botdan foydalanish huquqi yoq.")
        logger.warning(f"Ruxsatsiz kirish: {message.from_user.id} (@{message.from_user.username})")
        return
    return await handler(message, data)


@dp.message(F.voice)
async def voice_message_handler(message: Message):
    await handle_voice(message, bot)


@dp.message(Command("addtask"))
async def add_task_handler(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "📝 <b>Format:</b>\n"
            "<code>/addtask ish Vazifa nomi</code>\n"
            "<code>/addtask shaxsiy Vazifa nomi</code>\n\n"
            "Misol: <code>/addtask ish IT Infra variant tahlili</code>"
        )
        return

    db_type = args[1].lower()
    task_name = args[2]

    if db_type not in ["ish", "shaxsiy"]:
        await message.answer("❌ Faqat <code>ish</code> yoki <code>shaxsiy</code> deb yozing!")
        return

    await message.answer("⏳ Qo'shilmoqda...")
    result = await add_task(task_name, db_type)

    if result:
        await message.answer(
            f"✅ Vazifa qo'shildi!\n\n"
            f"💼 <b>{task_name}</b>\n"
            f"📂 {db_type.capitalize()} vazifalar"
        )
    else:
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")


@dp.message(Command("tasks"))
async def list_tasks_handler(message: Message):
    args = message.text.split()
    db_type = args[1].lower() if len(args) > 1 else "ish"
    filter_type = args[2].lower() if len(args) > 2 else "bugun"

    if db_type not in ["ish", "shaxsiy"]:
        db_type = "ish"

    await message.answer("⏳ Notion'dan yuklanmoqda...")
    tasks_text = await list_tasks(db_type, filter_type)
    await message.answer(tasks_text)


@dp.message(Command("done"))
async def done_task_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("✅ <b>Format:</b> <code>/done Vazifa nomi</code> (yoki qismi)")
        return

    task_name = args[1]
    await message.answer("⏳ Yangilanmoqda...")
    result = await complete_task(task_name)

    if result:
        await message.answer(f"✅ Bajarildi deb belgilandi!\n\n<b>{result}</b>")
    else:
        await message.answer("❌ Vazifa topilmadi. Nomni tekshiring.")


@dp.message(Command("today"))
async def today_handler(message: Message):
    await message.answer("📊 Bugungi vazifalar yuklanmoqda...")
    ish = await list_tasks("ish", "bugun")
    shaxsiy = await list_tasks("shaxsiy", "bugun")
    await message.answer(f"💼 <b>ISH:</b>\n{ish}\n\n🌿 <b>SHAXSIY:</b>\n{shaxsiy}")


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "👋 Salom! Men sizning shaxsiy AI assistantingizman.\n\n"
        "🎙️ <b>Ovozli xabar</b> yuboring — Gemini AI O'zbek tilida javob beradi\n\n"
        "📋 <b>Notion buyruqlari:</b>\n"
        "/addtask ish [vazifa] — Ish vazifasi qo'shish\n"
        "/addtask shaxsiy [vazifa] — Shaxsiy vazifa qo'shish\n"
        "/tasks ish bugun — Bugungi ish vazifalari\n"
        "/tasks shaxsiy hammasi — Barcha shaxsiy vazifalar\n"
        "/done [vazifa nomi] — Vazifani bajarildi qilish\n"
        "/today — Bugungi to'liq hisobot\n"
        "/help — Barcha buyruqlar"
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "📖 <b>Barcha buyruqlar:</b>\n\n"
        "🎙️ <b>Ovoz:</b>\n"
        "• Ovozli xabar yuboring — Gemini AI javob beradi\n\n"
        "📋 <b>Notion:</b>\n"
        "• /addtask ish [nom]\n"
        "• /addtask shaxsiy [nom]\n"
        "• /tasks ish bugun\n"
        "• /tasks ish ertaga\n"
        "• /tasks shaxsiy hammasi\n"
        "• /done [vazifa nomi]\n"
        "• /today\n\n"
        "⚙️ <b>Boshqa:</b>\n"
        "• /start — Boshlash\n"
        "• /help — Yordam"
    )


async def daily_scheduler():
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

            text = "☀️ <b>Xayrli tong! Bugungi reja:</b>\n\n"
            text += f"💼 <b>ISH:</b>\n{ish}\n\n"
            text += f"🌿 <b>SHAXSIY:</b>\n{shaxsiy}"
            if overdue:
                text += f"\n\n⚠️ <b>Muddati o'tgan:</b>\n{overdue}"

            await bot.send_message(CHAT_ID, text)
        except Exception as e:
            logger.error(f"Scheduler xatosi: {e}")


async def main():
    logger.info("Bot ishga tushmoqda... (Gemini 2.0 Flash Live Preview)")
    await asyncio.gather(
        dp.start_polling(bot),
        daily_scheduler()
    )

if __name__ == "__main__":
    asyncio.run(main())