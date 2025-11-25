# -*- coding: utf-8 -*-
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    JobQueue,
    filters,
)

# =========================
# إعدادات أساسية
# =========================

# توكن البوت
BOT_TOKEN = "8307758081:AAGRFcucb0XLWe6TEJAOX0qFFlMFYBpKSYY"  # <-- عدّلها

# آيدي القناة الخاصة (سالب مثل: -100xxxxxxxxxx)
CHANNEL_ID = -1002547907056            # <-- عدّلها

# آي دي الأدمن (ممكن أكثر من واحد)
ADMIN_IDS = {6671972850}               # <-- عدّلها

# ملفات التخزين
PLANS_FILE = "plans.json"          # تخزين الباقات
SUBS_FILE = "subscriptions.json"   # تخزين الاشتراكات

# باقات افتراضية أول تشغيل (تقدر تعدلها / تحذفها لاحقاً من داخل /admin)
DEFAULT_PLANS: Dict[str, Dict[str, Any]] = {
    "اشتراك أسبوعي": {"price": 100, "days": 7, "description": "وصول لمدة 7 أيام"},
    "اشتراك شهري": {"price": 300, "days": 30, "description": "وصول لمدة شهر"},
    "اشتراك دائم": {"price": 1000, "days": 3650, "description": "وصول طويل المدى"},
}

# كل كم ثانية يفحص انتهاء الاشتراكات (هنا كل ساعة)
CHECK_INTERVAL_SECONDS = 3600

# =========================
# لوق
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================
# دوال مساعدة - الباقات
# =========================

def load_plans() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(PLANS_FILE):
        save_plans(DEFAULT_PLANS)
        return DEFAULT_PLANS.copy()
    try:
        with open(PLANS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load plans file")
        return {}


def save_plans(plans: Dict[str, Dict[str, Any]]) -> None:
    try:
        with open(PLANS_FILE, "w", encoding="utf-8") as f:
            json.dump(plans, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save plans file")


# =========================
# دوال مساعدة - الاشتراكات
# =========================

def load_subs() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(SUBS_FILE):
        return {}
    try:
        with open(SUBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load subs file")
        return {}


def save_subs(subs: Dict[str, Dict[str, Any]]) -> None:
    try:
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save subs file")


def format_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================
# أمر /start للمستخدم
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    subs = load_subs()
    user_info = subs.get(str(user.id))

    if user_info:
        try:
            expires_at = datetime.fromisoformat(user_info["expires_at"])
            status = (
                f"✅ عندك اشتراك فعال حتى: <b>{format_dt(expires_at)} UTC</b>\n\n"
            )
        except Exception:
            status = "✅ عندك اشتراك مسجل، لكن تاريخ الانتهاء غير واضح.\n\n"
    else:
        status = "❌ ما عندك اشتراك فعال حالياً.\n\n"

    text = (
        f"هلا {user.first_name} 👋\n\n"
        + status
        + "اضغط الزر تحت لعرض الباقات المتاحة:"
    )

    keyboard = [
        [InlineKeyboardButton("📦 عرض الباقات", callback_data="user:show_plans")]
    ]
    await update.effective_message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


# =========================
# عرض الباقات للمستخدم
# =========================

async def user_show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    plans = load_plans()
    if not plans:
        await query.edit_message_text("🚫 لا توجد أي باقات متاحة حالياً.")
        return

    lines = []
    keyboard = []
    for name, info in plans.items():
        price = info.get("price", 0)
        days = info.get("days", 0)
        desc = info.get("description", "")
        duration_txt = "دائم" if days == 0 else f"{days} يوم"
        lines.append(f"• <b>{name}</b> – {duration_txt} – ⭐ {price}\n  <i>{desc}</i>")
        keyboard.append(
            [InlineKeyboardButton(f"{name} – ⭐{price}", callback_data=f"buy:{name}")]
        )

    text = "اختر الباقة اللي تناسبك 👇\n\n" + "\n".join(lines)

    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# إنشاء فاتورة Telegram Stars
# =========================

async def buy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    _, plan_name = data.split(":", 1)

    plans = load_plans()
    plan = plans.get(plan_name)
    if not plan:
        await query.edit_message_text("🚫 هذه الباقة لم تعد متاحة.")
        return

    price_stars = int(plan.get("price", 0))
    description = plan.get("description", "اشتراك في القناة الخاصة")

    # Telegram Stars: currency=XTR و amount = عدد النجوم
    prices = [LabeledPrice(label=plan_name, amount=price_stars)]
    payload = f"stars:{plan_name}:{price_stars}"

    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title=f"اشتراك – {plan_name}",
        description=description,
        payload=payload,
        provider_token="",  # فارغ مع Telegram Stars
        currency="XTR",
        prices=prices,
        max_tip_amount=0,
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False,
    )

    await query.edit_message_text(
        f"تم إنشاء طلب الاشتراك: <b>{plan_name}</b>\n"
        f"السعر: ⭐ {price_stars}\n\n"
        "رح يوصلك واجهة الدفع من تيليغرام، ادفع و انتظر تفعيل الاشتراك 👌",
        parse_mode="HTML",
    )


# =========================
# معالجة pre_checkout
# =========================

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    try:
        if not query.invoice_payload.startswith("stars:"):
            await query.answer(ok=False, error_message="Payload غير معروف.")
            return
        await query.answer(ok=True)
    except Exception as e:
        logger.error("Error in precheckout: %s", e)
        await query.answer(ok=False, error_message="صار خطأ، جرّب مرة ثانية.")


# =========================
# بعد الدفع الناجح
# =========================

async def successful_payment_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    payment = update.message.successful_payment
    user = update.effective_user

    payload = payment.invoice_payload or ""
    try:
        _, plan_name, price_str = payload.split(":", 2)
        price_stars = int(price_str)
    except Exception:
        plan_name = "باقتك"
        price_stars = payment.total_amount

    plans = load_plans()
    plan = plans.get(plan_name)
    if not plan:
        # في حال الباقة اختفت من الملف بعد الدفع
        plan = {"days": 0, "description": ""}

    days = int(plan.get("days", 0))
    now = datetime.utcnow()

    if days == 0:
        # دائم (نخلي التاريخ بعيد)
        expires_at = now + timedelta(days=3650)
    else:
        expires_at = now + timedelta(days=days)

    # إنشاء رابط دعوة للقناة
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
        )
        invite_link = invite.invite_link
    except Exception as e:
        logger.error("Error creating invite link: %s", e)
        invite_link = None

    # حفظ الاشتراك
    subs = load_subs()
    subs[str(user.id)] = {
        "plan": plan_name,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    save_subs(subs)

    lines = [
        "✅ تم الدفع بنجاح، يعطيك العافية!",
        f"📦 الباقة: <b>{plan_name}</b>",
        f"⭐ المبلغ المدفوع: {price_stars} نجمة",
        f"⏰ انتهاء الاشتراك (تقديرياً): <b>{format_dt(expires_at)} UTC</b>",
        "",
    ]

    if invite_link:
        lines.append("🔗 رابط الدخول للقناة الخاصة (اضغط للدخول):")
        lines.append(invite_link)
        lines.append("")
        lines.append("📌 الرابط صالح لدخول واحد فقط، لا تشاركه مع أحد.")
    else:
        lines.append("⚠ تم الدفع لكن ما قدرت أجهّز رابط دعوة للقناة.")
        lines.append("تواصل مع الأدمن لإكمال الاشتراك.")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# =========================
# لوحة تحكم الأدمن بالأزرار
# =========================

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    keyboard = [
        [InlineKeyboardButton("📦 عرض الباقات", callback_data="admin:show_plans")],
        [InlineKeyboardButton("➕ إضافة/تعديل باقة", callback_data="admin:add_plan")],
        [InlineKeyboardButton("🗑 حذف باقة", callback_data="admin:del_plan")],
        [InlineKeyboardButton("👥 عرض المشتركين", callback_data="admin:subs")],
    ]

    text = (
        "🛠 لوحة تحكم الأدمن\n\n"
        "➕ لإضافة/تعديل باقة: بعد الضغط على الزر، أرسل رسالة بالشكل:\n"
        "<code>اسم الباقة,السعر بالنجوم,عدد الأيام,وصف اختياري</code>\n"
        "مثال:\n"
        "<code>VIP أسبوعي,200,7,اشتراك أسبوعي مميز</code>\n\n"
        "🗑 لحذف باقة: اضغط الزر ثم أرسل اسم الباقة بالضبط.\n"
    )

    await update.effective_message.reply_text(
        text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("🚫 ما عندك صلاحية.")
        return

    data = query.data
    plans = load_plans()

    # عرض الباقات
    if data == "admin:show_plans":
        if not plans:
            await query.edit_message_text("🚫 لا توجد أي باقات حالياً.")
            return
        lines = []
        for name, info in plans.items():
            price = info.get("price", 0)
            days = info.get("days", 0)
            desc = info.get("description", "")
            dur = "دائم" if days == 0 else f"{days} يوم"
            lines.append(
                f"• <b>{name}</b> – ⭐{price} – {dur}\n  <i>{desc}</i>"
            )
        await query.edit_message_text(
            "📦 الباقات الحالية:\n\n" + "\n".join(lines),
            parse_mode="HTML",
        )

    # وضع إضافة/تعديل باقة
    elif data == "admin:add_plan":
        context.user_data["admin_mode"] = "add_plan"
        await query.edit_message_text(
            "أرسل الآن رسالة بصيغة:\n\n"
            "<code>اسم الباقة,السعر بالنجوم,عدد الأيام,وصف اختياري</code>\n"
            "مثال:\n"
            "<code>اشتراك أسبوعي,100,7,وصول لمدة أسبوع</code>",
            parse_mode="HTML",
        )

    # وضع حذف باقة
    elif data == "admin:del_plan":
        context.user_data["admin_mode"] = "del_plan"
        await query.edit_message_text(
            "أرسل اسم الباقة اللي تبي تحذفها بالضبط.\n\nمثال:\n"
            "<code>اشتراك أسبوعي</code>",
            parse_mode="HTML",
        )

    # عرض المشتركين
    elif data == "admin:subs":
        subs = load_subs()
        if not subs:
            await query.edit_message_text("👥 لا يوجد مشتركين مسجلين حالياً.")
            return
        lines = []
        now = datetime.utcnow()
        for uid, info in subs.items():
            plan_name = info.get("plan", "?")
            try:
                exp = datetime.fromisoformat(info["expires_at"])
                status = "✅ فعال" if exp > now else "⛔ منتهي"
                lines.append(
                    f"• ID {uid} – {plan_name} – ينتهي {format_dt(exp)} UTC – {status}"
                )
            except Exception:
                lines.append(f"• ID {uid} – {plan_name} – تاريخ غير معروف")
        await query.edit_message_text(
            "👥 المشتركين:\n\n" + "\n".join(lines),
            parse_mode="HTML",
        )


# =========================
# استقبال نصوص الأدمن (إضافة/حذف)
# =========================

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    mode = context.user_data.get("admin_mode")
    if not mode:
        return

    text = update.message.text.strip()
    plans = load_plans()

    # إضافة أو تعديل باقة
    if mode == "add_plan":
        # صيغة: اسم,سعر,أيام,وصف اختياري
        parts = [p.strip() for p in text.split(",", 3)]
        if len(parts) < 3:
            await update.message.reply_text(
                "❌ الصيغة غير صحيحة.\n"
                "استخدم:\n"
                "<code>اسم الباقة,السعر بالنجوم,عدد الأيام,وصف اختياري</code>",
                parse_mode="HTML",
            )
            return
        name = parts[0]
        try:
            price = int(parts[1])
            days = int(parts[2])
        except ValueError:
            await update.message.reply_text("❌ السعر والأيام لازم يكونوا أرقام.")
            return
        if len(parts) == 4:
            desc = parts[3]
        else:
            desc = f"اشتراك {name}"

        plans[name] = {"price": price, "days": days, "description": desc}
        save_plans(plans)

        await update.message.reply_text(
            f"✅ تم حفظ الباقة:\n"
            f"الاسم: {name}\n"
            f"السعر: ⭐{price}\n"
            f"المدة: {days} يوم\n"
            f"الوصف: {desc}"
        )
        context.user_data["admin_mode"] = None

    # حذف باقة
    elif mode == "del_plan":
        name = text
        if name not in plans:
            await update.message.reply_text("❌ لا توجد باقة بهذا الاسم.")
            return
        del plans[name]
        save_plans(plans)
        await update.message.reply_text(f"🗑 تم حذف الباقة: {name}")
        context.user_data["admin_mode"] = None


# =========================
# Job لفحص انتهاء الاشتراكات
# =========================

async def check_expired(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Running expiration check job...")
    subs = load_subs()
    now = datetime.utcnow()
    changed = False

    for uid_str, info in list(subs.items()):
        try:
            exp = datetime.fromisoformat(info["expires_at"])
        except Exception:
            continue

        if now >= exp:
            user_id = int(uid_str)
            logger.info("Subscription expired for user %s", user_id)
            # طرد العضو من القناة
            try:
                await context.bot.ban_chat_member(CHANNEL_ID, user_id)
                await context.bot.unban_chat_member(CHANNEL_ID, user_id)
            except Exception as e:
                logger.warning("Error kicking user %s: %s", user_id, e)

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏰ انتهى اشتراكك في القناة. إذا حابب تجدد، اكتب /start واختر باقة جديدة 💜",
                )
            except Exception:
                pass

            del subs[uid_str]
            changed = True

    if changed:
        save_subs(subs)
        logger.info("Expired subs cleaned.")


# =========================
# main
# =========================

def main() -> None:
    if BOT_TOKEN.startswith("PUT_") or not BOT_TOKEN:
        raise RuntimeError("رجاءً عدّل BOT_TOKEN و CHANNEL_ID و ADMIN_IDS في أعلى الملف.")

    application = Application.builder().token(BOT_TOKEN).build()

    # أوامر المستخدم
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_cmd))

    # أزرار المستخدم
    application.add_handler(
        CallbackQueryHandler(user_show_plans, pattern=r"^user:show_plans$")
    )
    application.add_handler(CallbackQueryHandler(buy_plan, pattern=r"^buy:"))

    # الدفع بالنجوم
    application.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    application.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler)
    )

    # أزرار الأدمن
    application.add_handler(CallbackQueryHandler(admin_buttons, pattern=r"^admin:"))

    # نصوص الأدمن (إضافة/حذف باقات)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(list(ADMIN_IDS)),
            admin_text,
        )
    )

    # Job لفحص انتهاء الاشتراكات
    job_queue: JobQueue = application.job_queue
    job_queue.run_repeating(
        check_expired, interval=CHECK_INTERVAL_SECONDS, first=CHECK_INTERVAL_SECONDS
    )

    logger.info("Bot is starting...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
