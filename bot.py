import json
import logging
from datetime import datetime, timedelta

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.ext import (
    Updater,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    PreCheckoutQueryHandler,
)

# ============== إعدادات أساسية ==============

# حط توكن بوتك هنا
BOT_TOKEN = "8307758081:AAGRFcucb0XLWe6TEJAOX0qFFlMFYBpKSYY"

# ID القناة الخاصة اللي بدك تربط فيها الدعوات (لازم يكون البوت أدمن بالقناة)
# مثال: -1001234567890
CHANNEL_ID = -1002547907056

# أرقام ID للمشرفين اللي لهم صلاحية /admin
ADMIN_IDS = {6671972850}

# ملف لتخزين المشتركين محلياً
DATA_FILE = "subscriptions.json"

# تعريف الخطط (تقدر تعدل الأيام والسعر براحتك)
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
        "days": 0,  # 0 يعني اشتراك دائم بدون انتهاء
        "price_stars": 10,
    },
}

# ============== أدوات مساعدة ==============


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        logging.exception("Failed to load data file")
        return {}


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logging.exception("Failed to save data file")


def get_user_sub(data, user_id):
    return data.get(str(user_id))


def set_user_sub(data, user_id, plan_key, expires_at):
    data[str(user_id)] = {
        "plan": plan_key,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    save_data(data)


def remove_user_sub(data, user_id):
    if str(user_id) in data:
        del data[str(user_id)]
        save_data(data)


def format_expiry(expires_at_str):
    if not expires_at_str:
        return "دائم"
    try:
        dt = datetime.fromisoformat(expires_at_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "غير معروف"


# ============== أوامر المستخدم ==============


def start(update: Update, context: CallbackContext):
    user = update.effective_user

    keyboard = [
        [
            InlineKeyboardButton("اشتراك أسبوعي ⭐", callback_data="plan_weekly"),
        ],
        [
            InlineKeyboardButton("اشتراك شهري ⭐", callback_data="plan_monthly"),
        ],
        [
            InlineKeyboardButton("اشتراك دائم ⭐", callback_data="plan_lifetime"),
        ],
        [
            InlineKeyboardButton("حالة اشتراكي 🔔", callback_data="my_status"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "👋 أهلاً حبيبي.\n\n"
        "اختر نوع الاشتراك اللي يناسبك من الأزرار تحت:\n\n"
        "كل اشتراك يتم عن طريق Telegram Stars داخل تيليغرام.\n"
    )

    update.message.reply_text(text, reply_markup=reply_markup)


def button(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    data = load_data()

    query.answer()

    # زر حالة الاشتراك
    if query.data == "my_status":
        sub = get_user_sub(data, user.id)
        if not sub:
            query.edit_message_text("🚫 ما عندك اشتراك فعال حالياً.")
        else:
            plan = PLANS.get(sub["plan"], {})
            plan_name = plan.get("name", "غير معروف")
            expires = format_expiry(sub.get("expires_at"))
            msg = f"🔔 حالة اشتراكك:\n\nالنوع: {plan_name}\nينتهي في: {expires}"
            query.edit_message_text(msg)
        return

    # اختيار خطة
    if not query.data.startswith("plan_"):
        return

    plan_key = query.data.replace("plan_", "")
    if plan_key not in PLANS:
        query.edit_message_text("❌ خطة غير معروفة.")
        return

    plan = PLANS[plan_key]

    title = plan["name"]
    description = f"{plan['name']} في القناة الخاصة."
    payload = f"sub_{plan_key}"
    currency = "XTR"  # عملة Telegram Stars
    prices = [LabeledPrice(label=plan["name"], amount=plan["price_stars"])]

    # نبعث الفاتورة للمستخدم (Telegram Stars)
    context.bot.send_invoice(
        chat_id=user.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # فاضي عشان Telegram Stars
        currency=currency,
        prices=prices,
    )

    query.edit_message_text(
        f"⭐ السعر: {plan['price_stars']} نجمة.\n"
        "رح يوصلك إشعار دفع من تيليغرام، وافق عليه لإكمال العملية. ✅"
    )


def precheckout_callback(update: Update, context: CallbackContext):
    query = update.pre_checkout_query

    # إذا في أي مشكلة بالدفع حط ok=False و reason
    if not query.invoice_payload.startswith("sub_"):
        query.answer(ok=False, error_message="🚫 نوع الدفع غير معروف.")
        return

    query.answer(ok=True)


def successful_payment(update: Update, context: CallbackContext):
    user = update.effective_user
    payment = update.message.successful_payment
    payload = payment.invoice_payload  # مثال sub_weekly

    plan_key = payload.replace("sub_", "")
    if plan_key not in PLANS:
        update.message.reply_text("تم الدفع، لكن الخطة غير معروفة. تواصل مع الادمن.")
        return

    plan = PLANS[plan_key]
    data = load_data()

    if plan["days"] > 0:
        expires_at = datetime.utcnow() + timedelta(days=plan["days"])
    else:
        expires_at = None  # اشتراك دائم

    # نخزن الاشتراك
    set_user_sub(data, user.id, plan_key, expires_at)

    # نعمل رابط دعوة للقناة ونرسله للمستخدم
    try:
        invite = context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
        )
        link = invite.invite_link
    except Exception:
        logging.exception("Failed to create invite link")
        link = None

    msg_lines = [
        "✅ تم استلام الدفع بنجاح!",
        f"الخطة: {plan['name']}",
    ]
    if plan["days"] > 0:
        msg_lines.append(f"المدة: {plan['days']} يوم")
    else:
        msg_lines.append("المدة: دائم")

    if link:
        msg_lines.append("")
        msg_lines.append("اضغط الرابط لدخول القناة الخاصة:")
        msg_lines.append(link)
    else:
        msg_lines.append("")
        msg_lines.append("❗ ما قدرت أجهز رابط دعوة للقناة.")
        msg_lines.append("تواصل مع الادمن لو ما وصلك اشتراكك.")

    update.message.reply_text("\n".join(msg_lines))


# ============== لوحة تحكم الادمن ==============


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        update.message.reply_text("🚫 ما عندك صلاحية الدخول للوحة التحكم.")
        return

    keyboard = [
        [
            InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("📄 قائمة المشتركين", callback_data="admin_list"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text("لوحة تحكم الأدمن:", reply_markup=reply_markup)


def admin_buttons(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = load_data()

    if not is_admin(user_id):
        query.answer("ما عندك صلاحية.", show_alert=True)
        return

    query.answer()

    if query.data == "admin_stats":
        total = len(data)
        active = 0
        now = datetime.utcnow()
        for sub in data.values():
            expires = sub.get("expires_at")
            if not expires:
                active += 1
                continue
            try:
                dt = datetime.fromisoformat(expires)
                if dt > now:
                    active += 1
            except Exception:
                continue

        text = (
            "📊 إحصائيات الاشتراكات:\n\n"
            f"إجمالي المستخدمين المسجلين: {total}\n"
            f"اشتراكات فعّالة: {active}\n"
        )
        query.edit_message_text(text)

    elif query.data == "admin_list":
        if not data:
            query.edit_message_text("ما في مشتركين مسجلين حالياً.")
            return

        lines = ["📄 قائمة أول 50 مشترك:"]
        now = datetime.utcnow()
        for i, (uid, sub) in enumerate(data.items()):
            if i >= 50:
                lines.append("... الخ")
                break
            plan = PLANS.get(sub["plan"], {})
            name = plan.get("name", sub["plan"])
            expires = sub.get("expires_at")
            status = "دائم"
            if expires:
                try:
                    dt = datetime.fromisoformat(expires)
                    status = dt.strftime("%Y-%m-%d")
                    if dt < now:
                        status += " (منتهي)"
                except Exception:
                    status = "غير معروف"
            lines.append(f"- {uid} | {name} | ينتهي: {status}")

        query.edit_message_text("\n".join(lines))


# ============== وظائف دورية ==============


def check_expired(context: CallbackContext):
    """تنفيذ دوري لحذف المشتركين المنتهين من القناة (لو أمكن)."""
    bot: Bot = context.bot
    data = load_data()
    now = datetime.utcnow()
    changed = False

    for uid, sub in list(data.items()):
        expires = sub.get("expires_at")
        if not expires:
            continue  # اشتراك دائم

        try:
            dt = datetime.fromisoformat(expires)
        except Exception:
            continue

        if dt <= now:
            user_id = int(uid)
            logging.info("Subscription expired for %s", user_id)
            # نحاول حذفه من القناة (لازم البوت يكون أدمن)
            try:
                bot.kick_chat_member(CHANNEL_ID, user_id)
                bot.unban_chat_member(CHANNEL_ID, user_id)  # عشان يقدر يرجع لو اشترك من جديد
            except Exception:
                logging.exception("Failed to remove user %s from channel", user_id)

            try:
                bot.send_message(
                    chat_id=user_id,
                    text="⏰ انتهى اشتراكك في القناة الخاصة. تقدر تجدد عن طريق /start 🌟",
                )
            except Exception:
                pass

            del data[uid]
            changed = True

    if changed:
        save_data(data)


# ============== تشغيل البوت ==============


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # أوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin))

    # أزرار عادية
    dp.add_handler(CallbackQueryHandler(button, pattern="^(plan_|my_status$)"))
    dp.add_handler(CallbackQueryHandler(admin_buttons, pattern="^admin_"))

    # الدفع
    dp.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    dp.add_handler(
        MessageHandler(Filters.successful_payment, successful_payment)
    )

    # وظيفة دورية لفحص الاشتراكات المنتهية كل ساعة
    job_queue = updater.job_queue
    job_queue.run_repeating(check_expired, interval=3600, first=3600)

    logging.info("Bot is starting...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
