import os
import re
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

# ========== ENV ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")

TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID"))  # -100...
SOURCE_CHANNEL_IDS = [
    int(x.strip()) for x in os.getenv("SOURCE_CHANNEL_IDS", "").split(",") if x.strip()
]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yo‘q")
if not TARGET_GROUP_ID:
    raise RuntimeError("TARGET_GROUP_ID yo‘q")
if not SOURCE_CHANNEL_IDS:
    raise RuntimeError("SOURCE_CHANNEL_IDS yo‘q")

# ========== LOG ==========
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("channel-sort-bot")

# ========== TOPIC IDS (SEN BERGAN) ==========
TOPIC_IDS = {
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

# ========== KEYWORDS ==========
KEYWORDS = {
    "uy": ["uy", "ijara", "kvartira", "xonadon", "arenda"],
    "ish": ["ish", "vakansiya", "job", "oylik"],
    "taksi": ["taksi", "uber", "careem", "transport"],
    "visa": ["visa", "viza", "iqoma", "pasport"],
    "bozor": ["narx", "bozor", "arzon", "qimmat"],
    "ziyorat": ["umra", "ziyorat", "makka", "madina", "miqot", "ehrom"],
    "salomatlik": ["kasal", "dori", "shifokor", "apteka"],
    "elon": ["sotiladi", "olinadi", "eʼlon", "elon"],
}

def detect_topic(text: str) -> int:
    if not text:
        return TOPIC_IDS["umumiy"]

    t = text.lower()
    for key, words in KEYWORDS.items():
        for w in words:
            if w in t:
                return TOPIC_IDS[key]

    return TOPIC_IDS["umumiy"]

# ========== HANDLER ==========
async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg:
        return

    if msg.chat.id not in SOURCE_CHANNEL_IDS:
        return

    text = msg.text or msg.caption or ""
    topic_id = detect_topic(text)

    try:
        await context.bot.send_message(
            chat_id=TARGET_GROUP_ID,
            message_thread_id=topic_id,
            text=text,
            disable_web_page_preview=False
        )
        log.info("Post joylandi → topic %s", topic_id)
    except Exception as e:
        log.error("Yuborishda xato: %s", e)

# ========== MAIN ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, on_channel_post))
    log.info("✅ Channel → Group sorter bot ishga tushdi")
    app.run_polling()

if __name__ == "__main__":
    main()
