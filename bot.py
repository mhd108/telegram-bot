# -*- coding: utf-8 -*-
import logging
import os
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

# =========================
# إعدادات أساسية
# =========================

# حط توكن البوت تبعك هون
BOT_TOKEN = "8307758081:AAFTrGOJAi_on0koLNkqNVJ5kIU_LI788KM"

# ID القناة الخاصة اللي بدك تبعت منها رابط الدعوة (لازم البوت يكون أدمن فيها)
# مثال: -1001234567890
CHANNEL_ID = -1002547907056

# أرقام الـ ID تبع المشرفين اللي لهم صلاحية /admin
ADMIN_IDS = {6671972850}  # حط الـ user_id تبعك هون

# تعريف الخطط (تقدر تعدّل الأيام والسعر براحتك)
PLANS = {
    "weekly": {
        "name": "اشتراك أسبوعي",
        "days": 7,
        "price_stars": 1,
    },
    "monthly": {
        "name": "اشتراك شهري",
        "days": 30,
        "price_stars": 3,
    },
    "lifetime": {
        "name": "اشتراك دائم",
        "days": 3650,  # عملياً دائم
        "price_stars": 10,
    },
}

# تخزين بسيط للاشتراكات في الذاكرة
# الشكل: user_id -> {"plan_id": ..., "expires_at": datetime}
user_subscriptions = {}

# =========================
# لوجينغ
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================
# دوال مساعدة
# =========================

def build_main_menu() -> InlineKeyboardMarkup:
    """لوحة الاشتراكات للمستخدم العادي."""
    keyboard = [
        [
            InlineKeyboardButton("📅 اشتراك أسبوعي", callback_data="plan:weekly"),
        ],
        [
            InlineKeyboardButton("📅 اشتراك شهري", callback_data="plan:monthly"),
        ],
        [
            InlineKeyboardButton("♾️ اشتراك دائم", callback_data="plan:lifetime"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_user_sub_info(user_id: int):
    info = user_subscriptions.get(user_id)
    if not info:
        return "لا يوجد لديك اشتراك فعّال حالياً."
    expires_at = info["expires_at"]
    if expires_at.year > 2100:
        return "لديك اشتراك دائم ✅"
    return f"اشتراكك فعّال حتى: {expires_at.strftime('%Y-%m-%d %H:%M')} ✅"


def stars_to_amount(stars: int) -> int:
    """
    قيمة الـ amount هي أقل وحدة للعملة.
    لعملات الفيات هي مثلاً سنتات، للنجوم مافي توثيق رسمي واضح،
    لكن عملياً نستخدم 100 * عدد النجوم، وغالباً رح تمشي.
    لو عندك رقم محدد كنت تستخدمه قبل، عدّله هون.
    """
    return stars * 100


# =========================
# أوامر
# =========================

def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    logger.info("User %s started the bot", user.id)

    text = (
        "هلا حبيبي 👋\n\n"
        "اختَر نوع الاشتراك اللي يناسبك من الأزرار تحت:\n"
    )

    sub_info = get_user_sub_info(user.id)
    text += f"\n🔔 حالة اشتراكك:\n{sub_info}"

    update.message.reply_text(text, reply_markup=build_main_menu())


def admin_cmd(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        update.message.reply_text("ما إلك صلاحية تستخدم أمر /admin 👮‍♂️")
        return

    text = (
        "لوحة تحكم الأدمن 👑\n\n"
        "حالياً التعديل يكون من داخل الكود مباشرة.\n"
        "الخطط الحالية:\n\n"
    )

    for pid, p in PLANS.items():
        text += f"- {p['name']}: {p['price_stars']} نجوم / {p['days']} يوم\n"

    update.message.reply_text(text, reply_markup=build_main_menu())


# =========================
# أزرار الإنلاين
# =========================

def handle_buttons(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = query.from_user
    data = query.data
    query.answer()

    if data.startswith("plan:"):
        plan_id = data.split(":", 1)[1]
        plan = PLANS.get(plan_id)
        if not plan:
            query.edit_message_text("الخطة غير معروفة، حاول مرة ثانية.")
            return

        # تحضير الفاتورة
        title = plan["name"]
        description = f"وصول إلى القناة الخاصة لمدة {plan['days']} يوم."
        payload = f"sub:{plan_id}"
        currency = "XTR"  # عملة النجوم
        prices = [LabeledPrice("Subscription", stars_to_amount(plan["price_stars"]))]

        logger.info("Sending invoice to user %s for plan %s", user.id, plan_id)

        try:
            context.bot.send_invoice(
                chat_id=user.id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # بتعامل مع Stars ببساطة، خليه فاضي
                currency=currency,
                prices=prices,
            )
            query.edit_message_text(
                f"السعر: {plan['price_stars']} ⭐\n"
                f"اضغط زر الدفع اللي رح يوصلك من تيليغرام لإكمال العملية."
            )
        except Exception as e:
            logger.exception("Failed to send invoice: %s", e)
            query.edit_message_text(
                "صار خطأ أثناء إرسال الفاتورة. تأكد أن البوت مفعّل للمدفوعات،"
                " أو جرّب بعدين."
            )

    else:
        query.edit_message_text("أمر غير معروف.")


# =========================
# الدفع
# =========================

def precheckout_callback(update: Update, context: CallbackContext) -> None:
    """يتنادى قبل ما تيليغرام يكمّل عملية الدفع."""
    query = update.pre_checkout_query
    payload = query.invoice_payload or ""

    if not payload.startswith("sub:"):
        query.answer(ok=False, error_message="Payload غير معروف.")
        return

    # كلشي تمام
    query.answer(ok=True)


def successful_payment_handler(update: Update, context: CallbackContext) -> None:
    """يتنادى بعد ما تيليغرام يأكد الدفع."""
    message = update.message
    user = message.from_user
    payment = message.successful_payment

    payload = payment.invoice_payload or ""
    logger.info("Successful payment from %s with payload %s", user.id, payload)

    if not payload.startswith("sub:"):
        message.reply_text("تم الدفع، لكن لم أستطع تحديد الخطة. تواصل مع الأدمن.")
        return

    plan_id = payload.split(":", 1)[1]
    plan = PLANS.get(plan_id)
    if not plan:
        message.reply_text("الخطة غير معروفة بعد الدفع. تواصل مع الأدمن.")
        return

    # حساب تاريخ الانتهاء
    if plan_id == "lifetime":
        expires_at = datetime(2999, 1, 1)  # عملياً دائم
    else:
        expires_at = datetime.utcnow() + timedelta(days=plan["days"])

    user_subscriptions[user.id] = {
        "plan_id": plan_id,
        "expires_at": expires_at,
    }

    # إنشاء رابط دعوة للقناة
    try:
        # رابط مخصص لعضو واحد، يعني ما حدا غيره يدخل منه
        invite_link = context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=None if plan_id == "lifetime" else int(expires_at.timestamp()),
        )
        link = invite_link.invite_link
    except Exception as e:
        logger.exception("Failed to create invite link: %s", e)
        link = None

    text = "✅ تم الدفع بنجاح!\n\n"
    text += f"الخطة: {plan['name']} ({plan['price_stars']} ⭐)\n"

    if plan_id == "lifetime":
        text += "المدة: اشتراك دائم.\n"
    else:
        text += f"المدة: {plan['days']} يوم.\n"
        text += f"تاريخ الانتهاء التقريبي: {expires_at.strftime('%Y-%m-%d %H:%M')} (UTC)\n"

    if link:
        text += f"\nرابط الدخول إلى القناة الخاصة:\n{link}\n\n"
        text += "لا تشارك الرابط مع أحد، صالح لمرة واحدة فقط."
    else:
        text += (
            "\n⚠️ تم الدفع لكن لم أستطع إنشاء رابط دعوة للقناة.\n"
            "تواصل مع الأدمن لإكمال اشتراكك."
        )

    message.reply_text(text)


# =========================
# الخطأ العام
# =========================

def error_handler(update: object, context: CallbackContext) -> None:
    logger.warning("Update %s caused error %s", update, context.error)


# =========================
# main
# =========================

def main() -> None:
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("انسخ توكن البوت الحقيقي داخل المتغير BOT_TOKEN قبل التشغيل.")

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # أوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin_cmd))

    # أزرار الإنلاين
    dp.add_handler(CallbackQueryHandler(handle_buttons))

    # الدفع
    dp.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    dp.add_handler(
        MessageHandler(Filters.successful_payment, successful_payment_handler)
    )

    # لوج للأخطاء
    dp.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
