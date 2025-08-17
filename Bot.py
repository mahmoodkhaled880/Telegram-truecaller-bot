import os, re, requests
from dotenv import load_dotenv
from phonenumbers import parse as pn_parse, format_number, PhoneNumberFormat, NumberParseException
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# تحميل المتغيرات من .env أو من Environment Variables على Render/Heroku
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{number}"

def normalize_number(raw: str) -> str | None:
    raw = re.sub(r"[^\d+]", "", (raw or "").strip())
    if not raw:
        return None
    try:
        if not raw.startswith("+"):
            return None
        num = pn_parse(raw, None)
        return format_number(num, PhoneNumberFormat.E164)
    except NumberParseException:
        return None

def lookup_twilio(number_e164: str) -> dict:
    params = {"fields": "line_type_intelligence,carrier,caller_name"}
    resp = requests.get(
        LOOKUP_URL.format(number=number_e164),
        params=params,
        auth=(TWILIO_SID, TWILIO_TOKEN),
        timeout=15
    )
    if resp.status_code == 404:
        return {"error": "الرقم غير موجود في خدمة البحث"}
    resp.raise_for_status()
    return resp.json()

def pretty_ar(info: dict, number: str) -> str:
    if "error" in info:
        return f"❌ {info['error']} ({number})"

    caller = info.get("caller_name") or {}
    carrier = info.get("carrier") or {}
    line = info.get("line_type_intelligence") or {}

    country = info.get("country_code") or "—"
    name = caller.get("caller_name") or "—"
    caller_type = caller.get("caller_type") or "—"
    carrier_name = carrier.get("name") or "—"
    network_type = carrier.get("type") or line.get("type") or "—"

    lines = [
        f"📞 الرقم: {number}",
        f"🌍 الدولة: {country}",
        f"👤 الاسم: {name}",
        f"🏷️ نوع المتصل: {caller_type}",
        f"📡 شركة الاتصال: {carrier_name}",
        f"🔌 نوع الخط: {network_type}",
    ]
    return "\n".join(lines)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً! أرسل رقم الهاتف بالتنسيق الدولي مثل:\n+14155552671\n"
        "سأحاول جلب الدولة/شركة الاتصال/نوع الخط، والاسم إذا متاح."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "طريقة الاستخدام:\n"
        "• أرسل الرقم بصيغة دولية يبدأ بـ +\n"
        "• مثال: +9705XXXXXXXX\n"
        "• ملاحظة: إظهار الاسم (CNAM) متاح غالبًا للأرقام الأمريكية فقط."
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    number = normalize_number(text)
    if not number:
        await update.message.reply_text("أرسل رقمًا بالتنسيق الدولي (مثال: +14155552671).")
        return
    try:
        info = lookup_twilio(number)
        await update.message.reply_text(pretty_ar(info, number))
    except requests.HTTPError as e:
        msg = f"خطأ من مزود الخدمة: {e.response.status_code}\n{e.response.text[:200]}"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ غير متوقع: {e}")

def build_app():
    if not all([BOT_TOKEN, TWILIO_SID, TWILIO_TOKEN]):
        raise RuntimeError("مفقود TELEGRAM_BOT_TOKEN أو TWILIO_ACCOUNT_SID أو TWILIO_AUTH_TOKEN")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app

if __name__ == "__main__":
    app = build_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)

