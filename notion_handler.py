import os
import httpx
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"

# Notion Database ID'lari
DB_IDS = {
    "ish": os.getenv("NOTION_ISH_DB_ID"),         # 💼 Ish Vazifalari
    "shaxsiy": os.getenv("NOTION_SHAXSIY_DB_ID")  # 🌿 Shaxsiy Vazifalar
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

HOLAT_EMOJI = {
    "No deadline": "⚪",
    "Muddati o'tgan": "🔴",
    "Bugun": "🟡",
    "Ertaga": "🔵",
    "Yaqin kunlarda": "🟣",
    "Bajarildi": "✅"
}

MUHIMLIK_EMOJI = {
    "🔴 Yuqori": "🔴",
    "🟡 O'rta": "🟡",
    "🟢 Past": "🟢"
}


async def add_task(task_name: str, db_type: str) -> bool:
    """Notion'ga yangi vazifa qo'shish"""
    db_id = DB_IDS.get(db_type)
    if not db_id:
        return False

    today = date.today().isoformat()

    # Kategoriya/Loyiha tanlash
    if db_type == "ish":
        extra_prop = {
            "Loyiha": {
                "multi_select": [{"name": "Boshqa"}]
            }
        }
    else:
        extra_prop = {
            "Kategoriya": {
                "multi_select": [{"name": "Boshqa"}]
            }
        }

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Vazifa nomi": {
                "title": [{"text": {"content": task_name}}]
            },
            "Holat": {
                "select": {"name": "Bugun"}
            },
            "Muhimlik": {
                "select": {"name": "🟡 O'rta"}
            },
            "Muddat": {
                "date": {"start": today}
            },
            **extra_prop
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers=HEADERS,
            json=payload
        )
        return response.status_code == 200


async def list_tasks(db_type: str, filter_type: str = "bugun") -> str:
    """Notion'dan vazifalarni olish"""
    db_id = DB_IDS.get(db_type)
    if not db_id:
        return "❌ Database topilmadi"

    today = date.today().isoformat()

    # Filter sozlash
    if filter_type == "bugun":
        status_filter = {"property": "Holat", "select": {"equals": "Bugun"}}
    elif filter_type == "ertaga":
        status_filter = {"property": "Holat", "select": {"equals": "Ertaga"}}
    elif filter_type == "muddati_otgan":
        status_filter = {"property": "Holat", "select": {"equals": "Muddati o'tgan"}}
    else:  # hammasi — bajarilmaganlar
        status_filter = {
            "property": "Holat",
            "select": {"does_not_equal": "Bajarildi"}
        }

    payload = {
        "filter": status_filter,
        "sorts": [
            {"property": "Muhimlik", "direction": "ascending"},
            {"property": "Muddat", "direction": "ascending"}
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=HEADERS,
            json=payload
        )

    if response.status_code != 200:
        return "❌ Notion'dan ma'lumot olishda xatolik"

    data = response.json()
    results = data.get("results", [])

    if not results:
        emoji = "💼" if db_type == "ish" else "🌿"
        return f"{emoji} Hozircha vazifalar yo'q!"

    # Natijani formatlash
    emoji = "💼" if db_type == "ish" else "🌿"
    text = f"{emoji} *{db_type.upper()} VAZIFALARI ({filter_type.upper()}):*\n\n"

    for i, page in enumerate(results, 1):
        props = page["properties"]

        # Vazifa nomi
        title_list = props.get("Vazifa nomi", {}).get("title", [])
        name = title_list[0]["text"]["content"] if title_list else "Nomsiz"

        # Holat
        holat_obj = props.get("Holat", {}).get("select")
        holat = holat_obj["name"] if holat_obj else "No deadline"
        holat_e = HOLAT_EMOJI.get(holat, "⚪")

        # Muhimlik
        muh_obj = props.get("Muhimlik", {}).get("select")
        muhimlik_e = MUHIMLIK_EMOJI.get(muh_obj["name"], "🟡") if muh_obj else "🟡"

        # Muddat
        muddat_obj = props.get("Muddat", {}).get("date")
        muddat = muddat_obj["start"] if muddat_obj else "—"

        text += f"{i}. {muhimlik_e} *{name}*\n"
        text += f"   {holat_e} {holat} | 📅 {muddat}\n\n"

    return text


async def complete_task(task_name_query: str) -> str | None:
    """Vazifani 'Bajarildi' ga o'zgartirish (ish va shaxsiy ikkisida ham qidiradi)"""

    for db_type, db_id in DB_IDS.items():
        if not db_id:
            continue

        # Barcha bajarilmaganlarni olib qidirish
        payload = {
            "filter": {
                "property": "Holat",
                "select": {"does_not_equal": "Bajarildi"}
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=HEADERS,
                json=payload
            )

        if response.status_code != 200:
            continue

        results = response.json().get("results", [])

        for page in results:
            title_list = page["properties"].get("Vazifa nomi", {}).get("title", [])
            name = title_list[0]["text"]["content"] if title_list else ""

            # Nom bo'yicha qidirish (kichik-katta harf farqi yo'q)
            if task_name_query.lower() in name.lower():
                page_id = page["id"]

                # Statusni yangilash
                async with httpx.AsyncClient() as client:
                    update_response = await client.patch(
                        f"https://api.notion.com/v1/pages/{page_id}",
                        headers=HEADERS,
                        json={
                            "properties": {
                                "Holat": {"select": {"name": "Bajarildi"}}
                            }
                        }
                    )

                if update_response.status_code == 200:
                    return name

    return None


async def send_overdue_tasks() -> str:
    """Muddati o'tgan vazifalarni ro'yxatini qaytarish"""
    text = ""

    for db_type, db_id in DB_IDS.items():
        if not db_id:
            continue

        payload = {
            "filter": {
                "property": "Holat",
                "select": {"equals": "Muddati o'tgan"}
            }
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=HEADERS,
                json=payload
            )

        if response.status_code != 200:
            continue

        results = response.json().get("results", [])
        if results:
            emoji = "💼" if db_type == "ish" else "🌿"
            text += f"{emoji} {db_type.upper()}:\n"
            for page in results:
                title_list = page["properties"].get("Vazifa nomi", {}).get("title", [])
                name = title_list[0]["text"]["content"] if title_list else "Nomsiz"
                text += f"  ⚠️ {name}\n"
            text += "\n"

    return text if text else ""
