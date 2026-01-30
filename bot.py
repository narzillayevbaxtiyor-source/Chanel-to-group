import os
import re
import json
import time
import logging
import asyncio
from typing import Dict, List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============ ENV ============
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_IDS_RAW = (os.getenv("ADMIN_IDS") or "").strip()
SOURCE_CHAT_ID = int((os.getenv("SOURCE_CHAT_ID") or "0").strip() or "0")
DEST_CHAT_ID = int((os.getenv("DEST_CHAT_ID") or "0").strip() or "0")

ADMIN_IDS: List[int] = []
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        if x.strip().lstrip("-").isdigit():
            ADMIN_IDS.append(int(x.strip()))

# ============ LOG ============
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("channel_to_group")

# ============ TOPICS ============
TOPICS = {
    "umumiy": 1,
    "uy": 197,
    "ish": 198,
    "taksi": 199,
    "visa": 200,
    "bozor": 201,
    "ziyorat": 202,
    "salomatlik": 203,
    "elon": 12,
}

TOPIC_LABELS = {
    "umumiy": "💬 Umumiy",
    "uy": "🏠 Uy / Ijara",
    "ish": "💼 Ish",
    "taksi": "🚖 Taksi",
    "visa": "🛂 Visa",
    "bozor": "🛒 Bozor",
    "ziyorat": "🕌 Ziyorat",
    "salomatlik": "🩺 Salomatlik",
    "elon": "📣 E’lon",
}

# ============ TO‘G‘RILANGAN KEYWORDS ============
DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "uy": [
        "ijara", "ijaraga", "arenda", "kvartira", "xonadon", "xona",
        "xonalik", "hostel", "mehmonxona", "mehmanxona",
        "hotel", "otel", "kunlik", "haftalik", "oylik",
        "room", "ko'yka", "койка", "yotoqxona"
    ],

    "ish": [
        "ish", "vakansiya", "работа", "job", "xodim", "ishchi",
        "maosh", "oylik", "kunlik ish", "rezume", "cv",
        "haydovchi", "driver", "kuryer", "operator"
    ],

    "taksi": [
        "taksi", "taxi", "careem", "uber", "bolt",
        "transfer", "airport", "aeroport",
        "haramdan", "nabaviydan", "uhudga",
        "ziyoratga olib bor"
    ],

    "visa": [
        "visa", "viza", "iqoma", "muqima",
        "absher", "jawazat", "passport", "pasport",
        "hujjat", "kafil", "sponsor", "jarima", "deport"
    ],

    "bozor": [
        "sotiladi", "sotaman", "olaman", "olamiz",
        "kuplyu", "prodam", "narx", "qancha",
        "savdo", "skidka", "chegirma",
        "magazin", "do'kon", "bozor"
    ],

    "ziyorat": [
        "umra", "ziyorat", "miqot", "ehrom", "ihram",
        "talbiya", "tavof", "sa'y", "duo",
        "haram", "ka'ba", "makk", "madin",
        "nabaviy", "rawza", "uhud", "baqi"
    ],

    "salomatlik": [
        "doktor", "shifokor", "klinika",
        "kasal", "dori", "apteka",
        "allergiya", "yo'tal", "isitma",
        "tish", "bosim", "qand"
    ],

    "elon": [
        "e'lon", "elon", "diqqat", "muhim",
        "announcement", "admin"
    ],
}

STATE_FILE = "state.json"

STATE = {
    "mode": "auto",
    "default_topic": "umumiy",
    "keywords": DEFAULT_KEYWORDS,
}

def load_state():
    global STATE
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                STATE.update(json.load(f))
        except Exception:
            pass

def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False, indent=2)

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())

def guess_topic(text: str) -> str:
    text = clean(text)
    for topic, words in STATE["keywords"].items():
        for w in words:
            if clean(w) in text:
                return topic
    return STATE.get("default_topic", "umumiy")

async def send_post(bot, msg, topic_key):
    thread_id = TOPICS.get(topic_key, 1)
    kw = {"message_thread_id": thread_id}

    caption = (msg.caption or msg.text or "")
    entities = msg.caption_entities or msg.entities

    if msg.photo:
        await bot.send_photo(DEST_CHAT_ID, msg.photo[-1].file_id, caption=caption, caption_entities=entities, **kw)
    elif msg.video:
        await bot.send_video(DEST_CHAT_ID, msg.video.file_id, caption=caption, caption_entities=entities, **kw)
    elif msg.document:
        await bot.send_document(DEST_CHAT_ID, msg.document.file_id, caption=caption, caption_entities=entities, **kw)
    else:
        await bot.send_message(DEST_CHAT_ID, caption, entities=entities, **kw)

async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or msg.chat_id != SOURCE_CHAT_ID:
        return

    text = msg.text or msg.caption or ""
    topic = guess_topic(text)

    await send_post(context.bot, msg, topic)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yo‘q")
    if not SOURCE_CHAT_ID or not DEST_CHAT_ID:
        raise RuntimeError("SOURCE_CHAT_ID / DEST_CHAT_ID yo‘q")

    load_state()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, on_channel_post))

    log.info("✅ Bot ishga tushdi (AUTO mode)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
