import logging
import json
import os
from datetime import datetime, time
from math import radians, sin, cos, sqrt, atan2

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_USERNAME = "Djuraev_ab"

AGENTS = {
    "+998975378555": {
        "name": "Шовкатов Шерзод Азимжонович",
        "zones": [
            {"name": "Yangi yo'l", "lat": 40.7821, "lon": 69.4214},
            {"name": "Oqqo'rg'on", "lat": 40.9108, "lon": 69.3326},
            {"name": "Chinoz", "lat": 40.9378, "lon": 68.7614},
        ]
    },
    "+998998759716": {
        "name": "Ёрқинов Хумоюн",
        "zones": [
            {"name": "Olmazor", "lat": 41.3317, "lon": 69.2239},
        ]
    }
}

CHECK_TIMES = [
    {"hour": 9, "minute": 0, "label": "Ertalabki 09:00"},
    {"hour": 14, "minute": 0, "label": "Tushki 14:00"},
]

RADIUS_KM = 1.0
daily_checks = {}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

def get_agent_by_phone(phone):
    clean = phone.replace(" ", "").replace("-", "")
    if not clean.startswith("+"):
        clean = "+" + clean
    return AGENTS.get(clean), clean

def is_in_zone(agent, user_lat, user_lon):
    for zone in agent["zones"]:
        dist = haversine(user_lat, user_lon, zone["lat"], zone["lon"])
        if dist <= RADIUS_KM:
            return True, zone["name"], dist
    closest = min(agent["zones"], key=lambda z: haversine(user_lat, user_lon, z["lat"], z["lon"]))
    dist = haversine(user_lat, user_lon, closest["lat"], closest["lon"])
    return False, closest["name"], dist

def get_current_check_label():
    now = datetime.now()
    for ct in CHECK_TIMES:
        h, m = ct["hour"], ct["minute"]
        check_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = abs((now - check_time).total_seconds())
        if diff <= 900:
            return ct["label"], f"checked_{h:02d}"
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("📍 Joylashuvimni yuborish", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Salom! 👋\n\nMen PrimeLink Agent Tracker botiman.\n\nAvval telefon raqamingizni yuboring:\nMasalan: +998971234567",
        reply_markup=reply_markup
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("+998") or text.startswith("998") or text.startswith("0"):
        agent, clean_phone = get_agent_by_phone(text)
        if agent:
            context.user_data["phone"] = clean_phone
            keyboard = [[KeyboardButton("📍 Joylashuvimni yuborish", request_location=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                f"✅ Salom, {agent['name']}!\n\nEndi 📍 tugmasini bosib joylashuvingizni yuboring.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Bu telefon raqam tizimda yo'q.\nTo'g'ri raqam kiriting: +998XXXXXXXXX")
    else:
        await update.message.reply_text("Iltimos, telefon raqamingizni kiriting.\nMasalan: +998971234567")

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = context.user_data.get("phone")
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    if now.weekday() == 6:
        await update.message.reply_text("Bugun yakshanba — ish kuni emas! 😊")
        return

    if not phone:
        await update.message.reply_text("Avval telefon raqamingizni yuboring!\nMasalan: +998971234567")
        return

    agent = AGENTS.get(phone)
    if not agent:
        await update.message.reply_text("❌ Siz tizimda ro'yxatdan o'tmagansiz.")
        return

    check_label, check_key = get_current_check_label()
    if not check_label:
        await update.message.reply_text(
            "⏰ Hozir tekshiruv vaqti emas.\nJoylashuv tekshiruv vaqtlarida qabul qilinadi:\n• 08:45 - 09:15\n• 13:45 - 14:15"
        )
        return

    agent_day_key = f"{phone}_{today}"
    if agent_day_key not in daily_checks:
        daily_checks[agent_day_key] = {}

    if daily_checks[agent_day_key].get(check_key):
        await update.message.reply_text(f"✅ {check_label} tekshiruvi allaqachon qabul qilingan!")
        return

    user_lat = update.message.location.latitude
    user_lon = update.message.location.longitude
    in_zone, zone_name, distance = is_in_zone(agent, user_lat, user_lon)
    daily_checks[agent_day_key][check_key] = True

    if in_zone:
        await update.message.reply_text(
            f"✅ Rahmat! Joylashuv qabul qilindi.\n\n🕐 Vaqt: {check_label}\n📍 Hudud: {zone_name}\n📏 Masofa: {distance:.2f} km"
        )
    else:
        await update.message.reply_text(
            f"⚠️ Diqqat! Siz belgilangan hududda emassiz.\n\n🕐 Vaqt: {check_label}\n📍 Eng yaqin hudud: {zone_name}\n📏 Masofa: {distance:.2f} km (limit: {RADIUS_KM} km)"
        )
    await notify_admin(context, agent["name"], phone, zone_name, distance, check_label, in_zone, now)

async def notify_admin(context, name, phone, zone, distance, check_label, in_zone, now):
    status = "✅ HUDUDDA" if in_zone else "❌ HUDUDDAN TASHQARIDA"
    msg = (
        f"📊 HISOBOT\n{'='*30}\n"
        f"👤 {name}\n📞 {phone}\n"
        f"🕐 {check_label} | {now.strftime('%d.%m.%Y %H:%M')}\n"
        f"📍 Hudud: {zone}\n📏 Masofa: {distance:.2f} km\n"
        f"{'='*30}\nHolat: {status}"
    )
    try:
        await context.bot.send_message(chat_id=f"@{ADMIN_USERNAME}", text=msg)
    except Exception as e:
        logger.error(f"Admin xabari yuborilmadi: {e}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    if username != ADMIN_USERNAME:
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"📊 Bugungi hisobot ({today})\n{'='*30}\n"
    for phone, agent in AGENTS.items():
        key = f"{phone}_{today}"
        checks = daily_checks.get(key, {})
        c09 = "✅" if checks.get("checked_09") else "❌"
        c14 = "✅" if checks.get("checked_14") else "❌"
        msg += f"\n👤 {agent['name']}\n   09:00 → {c09}  |  14:00 → {c14}\n"
    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hisobot", report))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
