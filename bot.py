import os
import re
import json
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
SOURCE_CHAT_ID = int((os.getenv("SOURCE_CHAT_ID") or "0").strip() or "0")   # channel id (-100...)
DEST_CHAT_ID = int((os.getenv("DEST_CHAT_ID") or "0").strip() or "0")       # group id (-100...)
BOT_USERNAME = (os.getenv("BOT_USERNAME") or "").strip().lstrip("@")        # optional

ADMIN_IDS: List[int] = []
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.split(","):
        x = x.strip()
        if x.lstrip("-").isdigit():
            ADMIN_IDS.append(int(x))

# ============ LOG ============
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("channel_to_group")

# ============ TOPICS (siz bergan kodlar) ============
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

TOPIC_LABELS_UZ = {
    "umumiy": "🧩 Umumiy",
    "uy": "🏠 Uy",
    "ish": "💼 Ish",
    "taksi": "🚖 Taksi",
    "visa": "🛂 Visa",
    "bozor": "🛒 Bozor",
    "ziyorat": "🕌 Ziyorat",
    "salomatlik": "🩺 Salomatlik",
    "elon": "📣 E’lon",
}

# ============ KEYWORDS -> TOPIC ============
# Siz xohlasangiz keyin admin paneldan o‘zgartirasiz
DEFAULT_KEYWORDS: Dict[str, List[str]] = {
    "uy": ["ijara", "kvartira", "uy", "xonadon", "room", "arenda", "ijaraga", "mehmanxona"],
    "ish": ["ish", "vakansiya", "vakans", "job", "работа", "xodim", "ishchi", "maosh", "o‘rin", "o'rin"],
    "taksi": ["taksi", "taxi", "careem", "uber", "transport", "mashina", "olib", "borib", "ketish", "narx"],
    "visa": ["visa", "viza", "iqoma", "muqim", "muqima", "hujjat", "passport", "pasport", "yurist"],
    "bozor": ["sotiladi", "olaman", "olamiz", "bozor", "narx", "arzon", "savdo", "магазин", "куплю", "продам"],
    "ziyorat": ["umra", "ziyorat", "maqom", "miqot", "ehrom", "ihram", "talbiya", "duo", "makk", "madin", "haram", "nabaviy", "uhud"],
    "salomatlik": ["doktor", "shifokor", "kasal", "og‘riq", "og'riq", "dori", "apteka", "allergiya", "tish", "yo‘tal", "yotal"],
    "elon": ["e'lon", "elon", "announcement", "diqqat", "важно", "ogohlantirish"],
}

STATE_FILE = "state.json"

DEFAULT_STATE = {
    "mode": "auto",              # auto | manual
    "default_topic": "umumiy",    # fallback
    "keywords": DEFAULT_KEYWORDS,
    "last_seen_channel_msg_id": 0,
}

STATE = {}

def load_state():
    global STATE
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                STATE = json.load(f) or {}
        except Exception:
            STATE = {}
    # merge defaults
    for k, v in DEFAULT_STATE.items():
        if k not in STATE:
            STATE[k] = v
    # ensure keys exist
    if "keywords" not in STATE or not isinstance(STATE["keywords"], dict):
        STATE["keywords"] = DEFAULT_KEYWORDS
    if "mode" not in STATE:
        STATE["mode"] = "auto"
    if "default_topic" not in STATE:
        STATE["default_topic"] = "umumiy"

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(STATE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("State save failed: %s", e)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def clean_text_for_match(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text

def guess_topic_key(text: str) -> str:
    """keywords bo‘yicha topic topadi, topmasa default_topic"""
    t = clean_text_for_match(text)
    kw = STATE.get("keywords", DEFAULT_KEYWORDS)

    # kuchliroq match uchun: uzun keywordlar oldin tekshirilsin
    for topic_key, words in kw.items():
        for w in sorted(words, key=len, reverse=True):
            w2 = clean_text_for_match(w)
            if w2 and w2 in t:
                return topic_key

    return STATE.get("default_topic", "umumiy")

def topic_thread_id(topic_key: str) -> int:
    return TOPICS.get(topic_key, TOPICS["umumiy"])

def admin_panel_kb() -> InlineKeyboardMarkup:
    mode = STATE.get("mode", "auto")
    mode_label = "✅ AUTO" if mode == "auto" else "🖐 MANUAL"
    default_key = STATE.get("default_topic", "umumiy")
    default_label = TOPIC_LABELS_UZ.get(default_key, default_key)

    kb = [
        [InlineKeyboardButton(f"Rejim: {mode_label}", callback_data="adm:toggle_mode")],
        [InlineKeyboardButton(f"Default: {default_label}", callback_data="adm:set_default")],
        [InlineKeyboardButton("🧠 Keywords ko‘rish", callback_data="adm:show_keywords")],
        [InlineKeyboardButton("♻️ Keywords defaultga qaytarish", callback_data="adm:reset_keywords")],
    ]
    return InlineKeyboardMarkup(kb)

def choose_topic_kb(prefix: str = "pick") -> InlineKeyboardMarkup:
    # 8 ta tugma + umumiy + elon (hammasi)
    order = ["umumiy", "uy", "ish", "taksi", "visa", "bozor", "ziyorat", "salomatlik", "elon"]
    rows = []
    row = []
    for k in order:
        row.append(InlineKeyboardButton(TOPIC_LABELS_UZ[k], callback_data=f"{prefix}:{k}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back")])
    return InlineKeyboardMarkup(rows)

# ============ MEDIA SENDER ============
async def send_to_group_with_media(bot, dest_chat_id: int, thread_id: int, msg):
    kwargs = {"message_thread_id": thread_id} if thread_id else {}

    caption = (msg.caption or msg.text or "")
    caption = caption[:1024] if caption else None
    entities = msg.caption_entities or msg.entities

    # PHOTO
    if msg.photo:
        file_id = msg.photo[-1].file_id
        await bot.send_photo(
            chat_id=dest_chat_id,
            photo=file_id,
            caption=caption,
            caption_entities=entities,
            **kwargs
        )
        return

    # VIDEO
    if msg.video:
        await bot.send_video(
            chat_id=dest_chat_id,
            video=msg.video.file_id,
            caption=caption,
            caption_entities=entities,
            supports_streaming=True,
            **kwargs
        )
        return

    # ANIMATION (gif)
    if msg.animation:
        await bot.send_animation(
            chat_id=dest_chat_id,
            animation=msg.animation.file_id,
            caption=caption,
            caption_entities=entities,
            **kwargs
        )
        return

    # DOCUMENT
    if msg.document:
        await bot.send_document(
            chat_id=dest_chat_id,
            document=msg.document.file_id,
            caption=caption,
            caption_entities=entities,
            **kwargs
        )
        return

    # VOICE
    if msg.voice:
        await bot.send_voice(
            chat_id=dest_chat_id,
            voice=msg.voice.file_id,
            caption=caption,
            caption_entities=entities,
            **kwargs
        )
        return

    # AUDIO
    if msg.audio:
        await bot.send_audio(
            chat_id=dest_chat_id,
            audio=msg.audio.file_id,
            caption=caption,
            caption_entities=entities,
            **kwargs
        )
        return

    # TEXT fallback
    text = (msg.text or msg.caption or "").strip()
    if text:
        await bot.send_message(chat_id=dest_chat_id, text=text[:4096], entities=msg.entities, **kwargs)

# ============ “MANUAL MODE” uchun pending ============
# channel_msg_id -> data
PENDING: Dict[int, Dict] = {}async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    txt = (
        "Assalomu alaykum!\n"
        "Bu bot source kanaldagi postlarni guruh bo‘limlariga avtomat joylaydi.\n\n"
        "Admin: /admin"
    )
    await update.message.reply_text(txt)

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Siz admin emassiz.")
        return
    await update.message.reply_text("🛠 Admin panel:", reply_markup=admin_panel_kb())

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user:
        return
    if not is_admin(q.from_user.id):
        await q.answer("⛔ Admin emas", show_alert=True)
        return

    data = q.data or ""
    if data == "adm:toggle_mode":
        STATE["mode"] = "manual" if STATE.get("mode") == "auto" else "auto"
        save_state()
        await q.answer("OK")
        await q.edit_message_reply_markup(reply_markup=admin_panel_kb())
        return

    if data == "adm:set_default":
        await q.answer("OK")
        await q.edit_message_text("Default bo‘limni tanlang:", reply_markup=choose_topic_kb(prefix="def"))
        return

    if data.startswith("def:"):
        topic_key = data.split(":", 1)[1]
        if topic_key in TOPICS:
            STATE["default_topic"] = topic_key
            save_state()
        await q.answer("✅ Saqlandi")
        await q.edit_message_text("🛠 Admin panel:", reply_markup=admin_panel_kb())
        return

    if data == "adm:show_keywords":
        kw = STATE.get("keywords", {})
        lines = []
        for k, words in kw.items():
            lines.append(f"{TOPIC_LABELS_UZ.get(k,k)}: {', '.join(words[:20])}{'…' if len(words)>20 else ''}")
        text = "🧠 Keywords:\n\n" + "\n".join(lines)
        await q.answer("OK")
        await q.message.reply_text(text[:4096])
        return

    if data == "adm:reset_keywords":
        STATE["keywords"] = DEFAULT_KEYWORDS
        save_state()
        await q.answer("✅ Qaytarildi")
        await q.edit_message_reply_markup(reply_markup=admin_panel_kb())
        return

    if data == "adm:back":
        await q.answer("OK")
        try:
            await q.edit_message_text("🛠 Admin panel:", reply_markup=admin_panel_kb())
        except Exception:
            pass
        return

    # Manual post tanlash: pick:<channel_msg_id>:<topic_key>
    if data.startswith("pick:"):
        # pick:<msgid>:<topic>
        parts = data.split(":")
        if len(parts) != 3:
            await q.answer("Xato", show_alert=True)
            return
        ch_msg_id = int(parts[1])
        topic_key = parts[2]
        pend = PENDING.get(ch_msg_id)
        if not pend:
            await q.answer("Bu post topilmadi (eskirib ketgan).", show_alert=True)
            return

        msg = pend["msg"]
        thread_id = topic_thread_id(topic_key)
        await send_to_group_with_media(context.bot, DEST_CHAT_ID, thread_id, msg)
        PENDING.pop(ch_msg_id, None)

        await q.answer("✅ Yuborildi")
        try:
            await q.edit_message_text(f"✅ Yuborildi: {TOPIC_LABELS_UZ.get(topic_key, topic_key)}")
        except Exception:
            pass
        return

async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Source kanal postlarini ushlaydi va guruhga bo‘limlab yuboradi.
    """
    msg = update.channel_post
    if not msg:
        return
    if msg.chat_id != SOURCE_CHAT_ID:
        return

    # Post matni/caption
    text = (msg.text or msg.caption or "").strip()

    mode = STATE.get("mode", "auto")

    if mode == "manual":
        # Adminlardan birinchisiga DM qilib “qaysi bo‘lim?” so‘raymiz
        if not ADMIN_IDS:
            log.warning("MANUAL rejim: ADMIN_IDS yo‘q, auto fallback.")
            mode = "auto"
        else:
            PENDING[msg.message_id] = {"msg": msg, "ts": time.time()}
            # admin DMga preview + tugmalar
            preview = "📥 Yangi post keldi. Qaysi bo‘limga yuboray?\n\n"
            if text:
                preview += (text[:500] + ("…" if len(text) > 500 else ""))
            else:
                preview += "(Matn yo‘q, media post)"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🧩 Umumiy", callback_data=f"pick:{msg.message_id}:umumiy"),
                 InlineKeyboardButton("🏠 Uy", callback_data=f"pick:{msg.message_id}:uy")],
                [InlineKeyboardButton("💼 Ish", callback_data=f"pick:{msg.message_id}:ish"),
                 InlineKeyboardButton("🚖 Taksi", callback_data=f"pick:{msg.message_id}:taksi")],
                [InlineKeyboardButton("🛂 Visa", callback_data=f"pick:{msg.message_id}:visa"),
                 InlineKeyboardButton("🛒 Bozor", callback_data=f"pick:{msg.message_id}:bozor")],
                [InlineKeyboardButton("🕌 Ziyorat", callback_data=f"pick:{msg.message_id}:ziyorat"),
                 InlineKeyboardButton("🩺 Salomatlik", callback_data=f"pick:{msg.message_id}:salomatlik")],
                [InlineKeyboardButton("📣 E’lon", callback_data=f"pick:{msg.message_id}:elon")],
            ])

            try:
                await context.bot.send_message(chat_id=ADMIN_IDS[0], text=preview, reply_markup=kb)
            except Exception as e:
                log.warning("Admin DM yuborilmadi: %s. Auto fallback.", e)
                mode = "auto"

    if mode == "auto":
        topic_key = guess_topic_key(text)
        thread_id = topic_thread_id(topic_key)
        await send_to_group_with_media(context.bot, DEST_CHAT_ID, thread_id, msg)

async def on_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ixtiyoriy: Guruhda kimdir yozsa — o‘chirish/ boshqa logic kerak bo‘lsa shu yer.
    Hozircha tegmaymiz.
    """
    return

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN yo‘q. Railway Variables’ga BOT_TOKEN qo‘ying.")
    if not SOURCE_CHAT_ID or not DEST_CHAT_ID:
        raise RuntimeError("SOURCE_CHAT_ID va DEST_CHAT_ID majburiy.")

    load_state()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^(adm:|def:|pick:)"))

    # source channel postlari
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, on_channel_post))

    # (ixtiyoriy) guruhdagi text handler (hozir ishlatilmaydi)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_text))

    log.info("✅ Channel-to-group bot ishga tushdi. Mode=%s | Default=%s", STATE.get("mode"), STATE.get("default_topic"))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
