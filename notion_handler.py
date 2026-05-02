import os
import httpx
from datetime import date
from dotenv import load_dotenv

load_dotenv(dotenv_path='env.example')

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_VERSION = "2022-06-28"

DB_IDS = {
    "ish": os.getenv("NOTION_ISH_DB_ID"),
    "shaxsiy": os.getenv("NOTION_SHAXSIY_DB_ID")
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
    db_id = DB_IDS.get(db_type)
    if not db_id:
        return False

    today = date.today().isoformat()

    extra_prop = (
        {"Loyiha": {"multi_select": [{"name": "Boshqa"}]}}
        if db_type == "ish"
        else {"Kategoriya": {"multi_select": [{"name": "Boshqa"}]}}
    )

    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            "Vazifa nomi": {"title": [{"text": {"content": task_name}}]},
            "Holat": {"select": {"name": "Bugun"}},
            "Muhimlik": {"select": {"name": "🟡 O'rta"}},
            "Muddat": {"date": {"start": today}},
            **extra_prop
        }
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.notion.com/v1/pages",
            headers=HEADERS,
            json=payload
        )
    return response.status_code == 200


async def list_tasks(db_type: str, filter_type: str = "bugun") -> str:
    db_id = DB_IDS.get(db_type)
    if not db_id:
        return "❌ Database topilmadi"

    filter_map = {
        "bugun": {"property": "Holat", "select": {"equals": "Bugun"}},
        "ertaga": {"property": "Holat", "select": {"equals": "Ertaga"}},
        "muddati_otgan": {"property": "Holat", "select": {"equals": "Muddati o'tgan"}},
    }
    status_filter = filter_map.get(
        filter_type,
        {"property": "Holat", "select": {"does_not_equal": "Bajarildi"}}
    )

    payload = {
        "filter": status_filter,
        "sorts": [
            {"property": "Muhimlik", "direction": "ascending"},
            {"property": "Muddat", "direction": "ascending"}
        ]
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=HEADERS,
            json=payload
        )

    if response.status_code != 200:
        return "❌ Notion'dan ma'lumot olishda xatolik"

    results = response.json().get("results", [])

    if not results:
        emoji = "💼" if db_type == "ish" else "🌿"
        return f"{emoji} Hozircha vazifalar yo'q!"

    emoji = "💼" if db_type == "ish" else "🌿"
    text = f"{emoji} <b>{db_type.upper()} ({filter_type.upper()}):</b>\n\n"

    for i, page in enumerate(results, 1):
        props = page["properties"]

        title_list = props.get("Vazifa nomi", {}).get("title", [])
        name = title_list[0]["text"]["content"] if title_list else "Nomsiz"

        holat_obj = props.get("Holat", {}).get("select")
        holat = holat_obj["name"] if holat_obj else "No deadline"
        holat_e = HOLAT_EMOJI.get(holat, "⚪")

        muh_obj = props.get("Muhimlik", {}).get("select")
        muhimlik_e = MUHIMLIK_EMOJI.get(muh_obj["name"], "🟡") if muh_obj else "🟡"

        muddat_obj = props.get("Muddat", {}).get("date")
        muddat = muddat_obj["start"] if muddat_obj else "—"

        text += f"{i}. {muhimlik_e} <b>{name}</b>\n"
        text += f"   {holat_e} {holat} | 📅 {muddat}\n\n"

    return text


async def complete_task(task_name_query: str) -> str | None:
    for db_type, db_id in DB_IDS.items():
        if not db_id:
            continue

        payload = {
            "filter": {"property": "Holat", "select": {"does_not_equal": "Bajarildi"}}
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=HEADERS,
                json=payload
            )

        if response.status_code != 200:
            continue

        for page in response.json().get("results", []):
            title_list = page["properties"].get("Vazifa nomi", {}).get("title", [])
            name = title_list[0]["text"]["content"] if title_list else ""

            if task_name_query.lower() in name.lower():
                page_id = page["id"]
                async with httpx.AsyncClient(timeout=10.0) as client:
                    update = await client.patch(
                        f"https://api.notion.com/v1/pages/{page_id}",
                        headers=HEADERS,
                        json={"properties": {"Holat": {"select": {"name": "Bajarildi"}}}}
                    )
                if update.status_code == 200:
                    return name

    return None


async def send_overdue_tasks() -> str:
    text = ""
    for db_type, db_id in DB_IDS.items():
        if not db_id:
            continue

        payload = {
            "filter": {"property": "Holat", "select": {"equals": "Muddati o'tgan"}}
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
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
            text += f"{emoji} <b>{db_type.upper()}:</b>\n"
            for page in results:
                title_list = page["properties"].get("Vazifa nomi", {}).get("title", [])
                name = title_list[0]["text"]["content"] if title_list else "Nomsiz"
                text += f"  ⚠️ {name}\n"
            text += "\n"

    return text