# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    PreCheckoutQueryHandler,
    CallbackContext,
)

# ================== إعدادات أساسية ==================

# حط توكن البوت تبعك هون
BOT_TOKEN = "8307758081:AAGRFcucb0XLWe6TEJAOX0qFFlMFYBpKSYY"

# ID القناة الخاصة اللي بدك تبعت لها الدعوات (لازم يكون البوت أدمن فيها)
# مثال: -1001234567890
CHANNEL_ID = -1002547907056

# أرقام الـ user_id للأدمنات المسموح لهم يدخلوا لوحة التحكم
ADMIN_IDS = {6671972850}  # عدّل الرقم لرقمك انت

# ملف تخزين الخطط (يتخزن على السيرفر، رح يروح لو عملت Deploy جديد)
PLANS_FILE = "plans.json"

# إعداد اللوجينغ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ================== تخزين و تحميل الخطط ==================

def load_plans():
    try:
        with open(PLANS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("plans", {})
    except FileNotFoundError:
        # أول تشغيل: نحط شوية خطط افتراضية
        plans = {
            "plan1": {"title": "اشتراك أسبوعي", "price_stars": 10, "days": 7},
            "plan2": {"title": "اشتراك شهري", "price_stars": 25, "days": 30},
            "plan3": {"title": "اشتراك دائم", "price_stars": 60, "days": 0},
        }
        save_plans(plans)
        return plans
    except Exception:
        logger.exception("Failed to load plans file")
        return {}


def save_plans(plans):
    try:
        with open(PLANS_FILE, "w", encoding="utf-8") as f:
            json.dump({"plans": plans}, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed to save plans file")


def generate_plan_id(plans):
    """نعطي ID جديد تلقائي للزر الجديد."""
    i = 1
    while True:
        pid = f"plan{i}"
        if pid not in plans:
            return pid
        i += 1


def stars_to_amount(stars: int) -> int:
    """
    amount للنجوم لازم يكون مضروب بـ 100 حسب عملة XTR.
    يعني لو بدك 10 نجوم → amount = 1000
    """
    return stars * 100


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ================== أوامر المستخدم ==================

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    plans = load_plans()

    if not plans:
        update.message.reply_text("ما في خطط حالياً. تواصل مع الأدمن.")
        return

    keyboard = []
    for pid, p in plans.items():
        title = p.get("title", "خطة بدون اسم")
        price = p.get("price_stars", 0)
        keyboard.append(
            [InlineKeyboardButton(f"{title} ⭐{price}", callback_data=f"user_plan:{pid}")]
        )

    text = (
        f"هلا {user.first_name or ''} 👋\n\n"
        "اختر نوع الاشتراك اللي يناسبك من الأزرار تحت.\n"
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text, reply_markup=reply_markup)


def user_plan_button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    plans = load_plans()

    query.answer()

    _, pid = query.data.split(":", 1)
    plan = plans.get(pid)
    if not plan:
        query.edit_message_text("الخطة غير موجودة (يمكن الأدمن حذفها).")
        return

    title = plan["title"]
    price = plan["price_stars"]
    days = plan["days"]

    desc = f"اشتراك: {title}\nالسعر: ⭐ {price}\n"
    if days == 0:
        desc += "المدة: دائم.\n"
    else:
        desc += f"المدة: {days} يوم.\n"

    keyboard = [
        [InlineKeyboardButton(f"ادفع ⭐ {price}", callback_data=f"user_pay:{pid}")],
        [InlineKeyboardButton("رجوع للقائمة", callback_data="user_back")],
    ]

    query.edit_message_text(desc, reply_markup=InlineKeyboardMarkup(keyboard))


def user_back(update: Update, context: CallbackContext):
    # رجوع لقائمة الخطط
    query = update.callback_query
    query.answer()
    fake_update = Update(
        update.update_id,
        message=query.message,
    )
    start(fake_update, context)


def user_pay_button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    plans = load_plans()
    query.answer()

    _, pid = query.data.split(":", 1)
    plan = plans.get(pid)
    if not plan:
        query.edit_message_text("الخطة غير موجودة.")
        return

    title = plan["title"]
    price_stars = plan["price_stars"]

    context.bot.send_invoice(
        chat_id=user.id,
        title=title,
        description=f"اشتراك {title} في القناة الخاصة.",
        payload=f"sub:{pid}",
        provider_token="",  # للنجوم نخليه فاضي
        currency="XTR",
        prices=[LabeledPrice(title, stars_to_amount(price_stars))],
    )

    query.edit_message_text(
        f"السعر: ⭐ {price_stars}\n"
        "رح يوصلك إشعار دفع من تيليجرام، وافق عليه لإكمال الاشتراك."
    )


# ================== الدفع بالنجوم ==================

def precheckout_handler(update: Update, context: CallbackContext):
    query = update.pre_checkout_query
    if not query.invoice_payload.startswith("sub:"):
        query.answer(ok=False, error_message="نوع الدفع غير معروف.")
        return
    query.answer(ok=True)


def successful_payment_handler(update: Update, context: CallbackContext):
    msg = update.message
    user = msg.from_user
    payment = msg.successful_payment
    payload = payment.invoice_payload

    if not payload.startswith("sub:"):
        msg.reply_text("وصل دفع غير معروف. تواصل مع الأدمن.")
        return

    _, pid = payload.split(":", 1)
    plans = load_plans()
    plan = plans.get(pid)
    if not plan:
        msg.reply_text("الخطة غير موجودة بعد الدفع، تواصل مع الأدمن.")
        return

    title = plan["title"]
    price = plan["price_stars"]
    days = plan["days"]

    # نحاول نعمل رابط دعوة واحد
    try:
        invite = context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
        )
        link = invite.invite_link
    except Exception as e:
        logger.exception("Failed to create invite link: %s", e)
        link = None

    text = [
        "✅ تم الدفع بنجاح!",
        f"الخطة: {title}",
        f"السعر: ⭐ {price}",
    ]
    if days == 0:
        text.append("المدة: دائم.")
    else:
        text.append(f"المدة: {days} يوم تقريباً من وقت الدفع.")

    if link:
        text.append("")
        text.append("🎁 رابط الدخول للقناة الخاصة:")
        text.append(link)
    else:
        text.append("")
        text.append("⚠ تم الدفع لكن ما قدرت أجهز رابط الدعوة.")
        text.append("تواصل مع الأدمن لإكمال الاشتراك.")

    msg.reply_text("\n".join(text))


# ================== لوحة تحكم الأدمن ==================

def admin_cmd(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        update.message.reply_text("ما عندك صلاحية تفتح لوحة الأدمن 🚫")
        return

    show_admin_main(update, context)


def show_admin_main(update_or_query, context: CallbackContext):
    if isinstance(update_or_query, Update) and update_or_query.message:
        send_func = update_or_query.message.reply_text
    else:
        q = update_or_query.callback_query
        send_func = q.edit_message_text

    keyboard = [
        [InlineKeyboardButton("📋 عرض الخطط", callback_data="admin:list")],
        [InlineKeyboardButton("➕ إضافة خطة جديدة", callback_data="admin:add")],
    ]
    send_func("لوحة تحكم الأدمن 👇", reply_markup=InlineKeyboardMarkup(keyboard))


def admin_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_admin(user_id):
        query.answer("ما عندك صلاحية.", show_alert=True)
        return

    data = query.data
    plans = load_plans()
    query.answer()

    # القائمة الرئيسية
    if data == "admin:main":
        show_admin_main(update, context)
        return

    # عرض الخطط
    if data == "admin:list":
        if not plans:
            query.edit_message_text(
                "ما في أي خطة حالياً.\n"
                "ضيف خطة جديدة من زر (إضافة خطة جديدة)."
            )
            return

        lines = ["📋 الخطط الحالية:\n"]
        keyboard = []
        for pid, p in plans.items():
            title = p.get("title", "بدون اسم")
            price = p.get("price_stars", 0)
            days = p.get("days", 0)
            dur = "دائم" if days == 0 else f"{days} يوم"
            lines.append(f"- {pid}: {title} | ⭐{price} | {dur}")
            keyboard.append(
                [InlineKeyboardButton(f"تعديل: {title}", callback_data=f"admin:edit:{pid}")]
            )

        keyboard.append(
            [InlineKeyboardButton("⬅ رجوع", callback_data="admin:main")]
        )

        query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # إضافة خطة جديدة (نبدأ بالمرحلة الأولى)
    if data == "admin:add":
        context.user_data.clear()
        context.user_data["admin_mode"] = "create_title"
        query.edit_message_text(
            "🆕 إنشاء خطة جديدة:\n\n"
            "اكتب الآن اسم الزر / الخطة (مثال: اشتراك ٣ أيام)."
        )
        return

    # تعديل خطة معيّنة
    if data.startswith("admin:edit:"):
        _, _, pid = data.split(":", 2)
        plan = plans.get(pid)
        if not plan:
            query.edit_message_text("الخطة غير موجودة.")
            return

        title = plan.get("title", "بدون اسم")
        price = plan.get("price_stars", 0)
        days = plan.get("days", 0)
        dur = "دائم" if days == 0 else f"{days} يوم"

        text = (
            f"تعديل الخطة: {pid}\n\n"
            f"الاسم الحالي: {title}\n"
            f"السعر الحالي: ⭐{price}\n"
            f"المدة الحالية: {dur}\n\n"
            "اختر ما تريد تعديله:"
        )

        keyboard = [
            [InlineKeyboardButton("✏ تغيير الاسم", callback_data=f"admin:edit_title:{pid}")],
            [InlineKeyboardButton("💰 تغيير السعر", callback_data=f"admin:edit_price:{pid}")],
            [InlineKeyboardButton("⏱ تغيير المدة", callback_data=f"admin:edit_days:{pid}")],
            [InlineKeyboardButton("🗑 حذف الخطة", callback_data=f"admin:delete:{pid}")],
            [InlineKeyboardButton("⬅ رجوع", callback_data="admin:list")],
        ]

        query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # حذف خطة
    if data.startswith("admin:delete:"):
        _, _, pid = data.split(":", 2)
        if pid in plans:
            del plans[pid]
            save_plans(plans)
            query.edit_message_text("✅ تم حذف الخطة.")
        else:
            query.edit_message_text("الخطة غير موجودة.")
        return

    # تغيير الاسم
    if data.startswith("admin:edit_title:"):
        _, _, pid = data.split(":", 2)
        if pid not in plans:
            query.edit_message_text("الخطة غير موجودة.")
            return

        context.user_data["admin_mode"] = "edit_title"
        context.user_data["edit_pid"] = pid
        query.edit_message_text(
            f"✏ أرسل الاسم الجديد للخطة:\n(current: {plans[pid]['title']})"
        )
        return

    # تغيير السعر
    if data.startswith("admin:edit_price:"):
        _, _, pid = data.split(":", 2)
        if pid not in plans:
            query.edit_message_text("الخطة غير موجودة.")
            return

        context.user_data["admin_mode"] = "edit_price"
        context.user_data["edit_pid"] = pid
        query.edit_message_text(
            f"💰 أرسل السعر الجديد بالنجوم (رقم فقط):\n(current: {plans[pid]['price_stars']})"
        )
        return

    # تغيير المدة
    if data.startswith("admin:edit_days:"):
        _, _, pid = data.split(":", 2)
        if pid not in plans:
            query.edit_message_text("الخطة غير موجودة.")
            return

        context.user_data["admin_mode"] = "edit_days"
        context.user_data["edit_pid"] = pid
        query.edit_message_text(
            f"⏱ أرسل المدة الجديدة بالأيام (0 = دائم):\n(current: {plans[pid]['days']})"
        )
        return


def admin_text_handler(update: Update, context: CallbackContext):
    """هاندلر لنصوص الأدمن لما نكون بوضع تعديل/إضافة."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    text = update.message.text.strip()
    mode = context.user_data.get("admin_mode")
    plans = load_plans()

    # ما في مود شغّال
    if not mode:
        return

    # إنشاء خطة جديدة - الخطوة 1 (الاسم)
    if mode == "create_title":
        context.user_data["new_plan_title"] = text
        context.user_data["admin_mode"] = "create_price"
        update.message.reply_text(
            f"الاسم: {text}\n\n"
            "💰 أرسل الآن السعر بالنجوم (رقم فقط، مثال: 10)."
        )
        return

    # إنشاء خطة جديدة - الخطوة 2 (السعر)
    if mode == "create_price":
        try:
            price = int(text)
        except ValueError:
            update.message.reply_text("⚠ السعر لازم يكون رقم صحيح. جرّب مرة ثانية.")
            return

        context.user_data["new_plan_price"] = price
        context.user_data["admin_mode"] = "create_days"
        update.message.reply_text(
            f"السعر: ⭐{price}\n\n"
            "⏱ أرسل الآن المدة بالأيام (0 = دائم)."
        )
        return

    # إنشاء خطة جديدة - الخطوة 3 (الأيام)
    if mode == "create_days":
        try:
            days = int(text)
        except ValueError:
            update.message.reply_text("⚠ المدة لازم تكون رقم. جرّب مرة ثانية.")
            return

        title = context.user_data.get("new_plan_title", "خطة بدون اسم")
        price = context.user_data.get("new_plan_price", 0)

        pid = generate_plan_id(plans)
        plans[pid] = {
            "title": title,
            "price_stars": price,
            "days": max(days, 0),
        }
        save_plans(plans)

        context.user_data.clear()

        update.message.reply_text(
            "✅ تم إنشاء الخطة الجديدة:\n\n"
            f"ID: {pid}\n"
            f"الاسم: {title}\n"
            f"السعر: ⭐{price}\n"
            f"المدة: {'دائم' if days == 0 else str(days) + ' يوم'}"
        )
        return

    # تعديل اسم خطة
    if mode == "edit_title":
        pid = context.user_data.get("edit_pid")
        if not pid or pid not in plans:
            update.message.reply_text("الخطة غير موجودة.")
        else:
            plans[pid]["title"] = text
            save_plans(plans)
            update.message.reply_text(
                f"✅ تم تغيير اسم الخطة ({pid}) إلى: {text}"
            )
        context.user_data.clear()
        return

    # تعديل سعر خطة
    if mode == "edit_price":
        pid = context.user_data.get("edit_pid")
        try:
            price = int(text)
        except ValueError:
            update.message.reply_text("⚠ السعر لازم يكون رقم. جرّب مرة ثانية.")
            return

        if not pid or pid not in plans:
            update.message.reply_text("الخطة غير موجودة.")
        else:
            plans[pid]["price_stars"] = price
            save_plans(plans)
            update.message.reply_text(
                f"✅ تم تغيير السعر للخطة ({pid}) إلى ⭐{price}"
            )
        context.user_data.clear()
        return

    # تعديل مدة خطة
    if mode == "edit_days":
        pid = context.user_data.get("edit_pid")
        try:
            days = int(text)
        except ValueError:
            update.message.reply_text("⚠ المدة لازم تكون رقم. جرّب مرة ثانية.")
            return

        if not pid or pid not in plans:
            update.message.reply_text("الخطة غير موجودة.")
        else:
            plans[pid]["days"] = max(days, 0)
            save_plans(plans)
            update.message.reply_text(
                f"✅ تم تغيير المدة للخطة ({pid}) إلى: "
                f"{'دائم' if days == 0 else str(days) + ' يوم'}"
            )
        context.user_data.clear()
        return


# ================== تشغيل البوت ==================

def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("حط توكن البوت الحقيقي في BOT_TOKEN قبل التشغيل.")

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # أوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin_cmd))

    # أزرار المستخدم
    dp.add_handler(CallbackQueryHandler(user_plan_button, pattern=r"^user_plan:"))
    dp.add_handler(CallbackQueryHandler(user_pay_button, pattern=r"^user_pay:"))
    dp.add_handler(CallbackQueryHandler(user_back, pattern=r"^user_back$"))

    # أزرار الأدمن
    dp.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))

    # نصوص الأدمن (إضافة/تعديل خطط)
    dp.add_handler(
        MessageHandler(Filters.text & Filters.private & ~Filters.command, admin_text_handler)
    )

    # الدفع
    dp.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    dp.add_handler(MessageHandler(Filters.successful_payment, successful_payment_handler))

    logger.info("Bot is starting with dynamic admin panel…")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
