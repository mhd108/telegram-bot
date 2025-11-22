import logging
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
)

# ================= إعدادات أساسية =================
BOT_TOKEN = "8307758081:AAFTrGOJAi_on0koLNkqNVJ5kIU_LI788KM"   # << حط توكن البوت هنا
ADMIN_ID = 6671972850                    # << حط Telegram ID تبعك (رقم حسابك)
CHANNEL_ID = -1002547907056             # << بعد ما تطلع ID القناة بالفوروارد، حطه هنا

# خطط الاشتراك (مفاتيح داخلية: weekly / monthly / lifetime)
PLANS: Dict[str, Dict[str, Any]] = {
    "weekly": {
        "title": "📅 اشتراك أسبوعي",
        "description": "وصول إلى القناة الخاصة لمدة أسبوع.",
        "price_stars": 50,
        "days": 7,
    },
    "monthly": {
        "title": "📆 اشتراك شهري",
        "description": "وصول إلى القناة الخاصة لمدة شهر.",
        "price_stars": 150,
        "days": 30,
    },
    "lifetime": {
        "title": "♾ اشتراك دائم",
        "description": "وصول دائم إلى القناة الخاصة.",
        "price_stars": 300,
        "days": None,  # None = بدون انتهاء
    },
}

# ================= لوج =================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ADMIN_ID)


# ================= /id — يطبع chat_id للمحادثة الحالية =================
async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    cid = chat.id
    await update.message.reply_text(f"chat_id = {cid}")
    print("CHAT ID:", cid)


# ================= فوروارد رسالة من القناة للبوت → يرجع ID القناة =================
async def forward_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    origin = msg.forward_origin  # الإصدار الجديد من المكتبة

    # لو مو فوروارد من قناة
    if origin is None or not hasattr(origin, "chat") or origin.chat is None:
        await msg.reply_text("اعمِل فوروارد لرسالة من القناة نفسها للبوت، مو تكتب /id.")
        return

    chat = origin.chat
    cid = chat.id
    title = chat.title or "بدون اسم"

    await msg.reply_text(f"القناة: {title}\nchat_id = {cid}")
    print("FORWARDED CHANNEL ID:", cid)


# ================= /start =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"هلا {user.first_name or ''} 👋\n\n"
        "اختر نوع الاشتراك اللي يناسبك:"
    )

    keyboard = [
        [InlineKeyboardButton(plan["title"], callback_data=f"plan:{key}")]
        for key, plan in PLANS.items()
    ]

    await update.message.reply_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================= شاشة تفاصيل الخطة =================
async def plan_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":", 1)[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await query.edit_message_text("الخطة غير موجودة، جرّب مرة ثانية.")
        return

    price = plan["price_stars"]
    title = plan["title"]
    desc = plan["description"]

    text = (
        f"{title}\n\n"
        f"{desc}\n\n"
        f"السعر: ⭐ {price} نجمة.\n"
        "اضغط زر الدفع لإكمال الاشتراك."
    )

    keyboard = [
        [InlineKeyboardButton(f"💰 ادفع ⭐ {price}", callback_data=f"pay:{plan_key}")],
        [InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_main")],
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================= إنشاء فاتورة النجوم =================
async def pay_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":", 1)[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await query.edit_message_text("صار خطأ أثناء تجهيز الفاتورة.")
        return

    chat_id = query.message.chat_id
    title = plan["title"]
    desc = plan["description"]
    price_stars = plan["price_stars"]

    amount = price_stars
    prices = [LabeledPrice(label=title, amount=amount)]

    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=desc,
            payload=plan_key,
            provider_token="",     # للنجوم خليها فاضية
            currency="XTR",
            prices=prices,
        )
    except Exception as e:
        logger.error("Invoice error: %s", e)
        await query.edit_message_text(
            f"صار خطأ أثناء إنشاء الفاتورة:\n`{e}`",
            parse_mode="Markdown",
        )


# ================= رجوع للقائمة الرئيسية =================
async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = "رجعناك لقائمة الاشتراكات، اختر نوع الاشتراك:"
    keyboard = [
        [InlineKeyboardButton(plan["title"], callback_data=f"plan:{key}")]
        for key, plan in PLANS.items()
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================= pre_checkout (إجباري) =================
async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


# ================= وظيفة إزالة المستخدم من القناة =================
async def remove_from_channel(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user_id = data["user_id"]
    plan_key = data["plan_key"]

    try:
        await context.bot.ban_chat_member(CHANNEL_ID, user_id)
        await context.bot.unban_chat_member(CHANNEL_ID, user_id)

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"انتهى اشتراكك في: {PLANS[plan_key]['title']} ✅\n"
                    f"لو حاب تجدد الاشتراك، ادخل على البوت واشترك من جديد."
                ),
            )
        except Exception:
            pass

        logger.info("Removed user %s from channel (plan %s)", user_id, plan_key)
    except Exception as e:
        logger.error("Failed to remove user %s from channel: %s", user_id, e)


# ================= استلام دفع ناجح =================
async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    payment = msg.successful_payment

    plan_key = payment.invoice_payload
    plan = PLANS.get(plan_key)

    if not plan:
        await msg.reply_text("وصل دفع لخطة غير معروفة، تواصل مع الدعم.")
        return

    stars_paid = payment.total_amount
    days = plan["days"]

    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
        )
        invite_link = invite.invite_link
    except Exception as e:
        logger.error("Failed to create invite link: %s", e)
        await msg.reply_text(
            "✅ تم الدفع، لكن صار خطأ أثناء إنشاء رابط الدعوة.\n"
            "تواصل مع الأدمن لإتمام الاشتراك."
        )
        return

    base_text = (
        f"✅ تم الدفع بنجاح!\n"
        f"الخطة: {plan['title']}\n"
        f"المبلغ: ⭐ {stars_paid} نجمة.\n\n"
        f"🎁 هذا رابط الدخول للقناة الخاصة:\n{invite_link}\n"
    )

    if days is None:
        extra = "\nاشتراكك دائم، ما له تاريخ انتهاء."
    else:
        extra = (
            "\nاشتراكك مؤقت، وسيتم إنهاء وصولك تلقائياً بعد "
            f"{days} يوم/أيام."
        )

    await msg.reply_text(base_text + extra)

    if days is not None:
        seconds = days * 24 * 60 * 60
        context.job_queue.run_once(
            remove_from_channel,
            when=seconds,
            data={"user_id": msg.from_user.id, "plan_key": plan_key},
            name=f"sub_{msg.from_user.id}_{plan_key}",
        )


# ================= لوحة تحكم أدمِن =================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    lines = ["لوحة تحكم الاشتراكات 🛠", ""]
    for key, plan in PLANS.items():
        lines.append(
            f"- {plan['title']} | السعر الحالي: ⭐ {plan['price_stars']}"
        )

    text = "\n".join(lines) + "\n\nاختر الخطة لتعديلها أو أضف خطة جديدة:"

    keyboard = [
        [InlineKeyboardButton(plan["title"], callback_data=f"admin_plan:{key}")]
        for key, plan in PLANS.items()
    ]
    keyboard.append(
        [InlineKeyboardButton("➕ إضافة خطة/زر جديد", callback_data="admin_add")]
    )

    await update.message.reply_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_plan_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":", 1)[1]
    plan = PLANS.get(plan_key)
    if not plan:
        await query.edit_message_text("الخطة غير موجودة.")
        return

    text = (
        f"تعديل: {plan['title']}\n"
        f"السعر الحالي: ⭐ {plan['price_stars']}\n\n"
        "غيّر السعر أو الاسم من الأزرار:"
    )

    keyboard = [
        [
            InlineKeyboardButton("⭐ 20", callback_data=f"admin_price:{plan_key}:20"),
            InlineKeyboardButton("⭐ 50", callback_data=f"admin_price:{plan_key}:50"),
        ],
        [
            InlineKeyboardButton("⭐ 100", callback_data=f"admin_price:{plan_key}:100"),
            InlineKeyboardButton("⭐ 200", callback_data=f"admin_price:{plan_key}:200"),
        ],
        [
            InlineKeyboardButton("✏ سعر يدوي", callback_data=f"admin_custom_price:{plan_key}"),
            InlineKeyboardButton("📝 تغيير الاسم", callback_data=f"admin_custom_title:{plan_key}"),
        ],
        [
            InlineKeyboardButton("⬅ رجوع للوحة التحكم", callback_data="admin_back"),
        ],
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_set_price_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, plan_key, price_str = query.data.split(":")
    price = int(price_str)

    if plan_key not in PLANS:
        await query.edit_message_text("الخطة غير موجودة.")
        return

    PLANS[plan_key]["price_stars"] = price
    await query.edit_message_text(
        f"تم تحديث سعر {PLANS[plan_key]['title']} إلى ⭐ {price}.\n"
        "اكتب /admin لو حاب تشوف الأسعار الجديدة.",
    )


async def admin_custom_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.edit_message_text("الخطة غير موجودة.")
        return

    context.user_data["waiting_price_for"] = plan_key
    context.user_data.pop("waiting_title_for", None)
    context.user_data.pop("new_plan_stage", None)

    await query.edit_message_text(
        f"أرسل الآن رقم السعر الجديد بالنجوم لخطة:\n{PLANS[plan_key]['title']}\n\nمثال: 75"
    )


async def admin_custom_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.edit_message_text("الخطة غير موجودة.")
        return

    context.user_data["waiting_title_for"] = plan_key
    context.user_data.pop("waiting_price_for", None)
    context.user_data.pop("new_plan_stage", None)

    await query.edit_message_text(
        f"اكتب الآن الاسم الجديد لهذه الخطة:\n(الاسم هو اللي يظهر للناس في الأزرار)\n\n"
        f"الاسم الحالي: {PLANS[plan_key]['title']}"
    )


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fake_update = Update(
        update.update_id,
        message=update.effective_message,
    )
    await admin_panel(fake_update, context)


async def admin_add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["new_plan_stage"] = "title"
    context.user_data["new_plan"] = {}

    await query.edit_message_text(
        "إضافة خطة جديدة:\n"
        "1️⃣ أرسل اسم الزر/الخطة (مثال: اشتراك ٣ أيام)."
    )


async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    text = update.message.text.strip()

    if "waiting_price_for" in context.user_data:
        plan_key = context.user_data["waiting_price_for"]
        try:
            price = int(text)
        except ValueError:
            await update.message.reply_text("السعر لازم يكون رقم. مثال: 80")
            return

        if plan_key not in PLANS:
            await update.message.reply_text("الخطة غير موجودة.")
        else:
            PLANS[plan_key]["price_stars"] = price
            await update.message.reply_text(
                f"تم تحديث سعر {PLANS[plan_key]['title']} إلى ⭐ {price}."
            )

        context.user_data.pop("waiting_price_for", None)
        return

    if "waiting_title_for" in context.user_data:
        plan_key = context.user_data["waiting_title_for"]
        if plan_key not in PLANS:
            await update.message.reply_text("الخطة غير موجودة.")
        else:
            PLANS[plan_key]["title"] = text
            await update.message.reply_text(
                f"تم تغيير اسم الخطة إلى: {text}"
            )
        context.user_data.pop("waiting_title_for", None)
        return

    if "new_plan_stage" in context.user_data:
        stage = context.user_data["new_plan_stage"]
        new_plan = context.user_data.get("new_plan", {})

        if stage == "title":
            new_plan["title"] = text
            context.user_data["new_plan"] = new_plan
            context.user_data["new_plan_stage"] = "price"
            await update.message.reply_text(
                f"اسم الخطة: {text}\n\n2️⃣ أرسل السعر بالنجوم (مثال: 40)."
            )
            return

        if stage == "price":
            try:
                price = int(text)
            except ValueError:
                await update.message.reply_text("السعر لازم يكون رقم. مثال: 40")
                return
            new_plan["price_stars"] = price
            context.user_data["new_plan"] = new_plan
            context.user_data["new_plan_stage"] = "days"
            await update.message.reply_text(
                "3️⃣ أرسل مدة الاشتراك بالأيام:\n"
                "- مثال: 7 = أسبوع\n"
                "- 30 = شهر\n"
                "- 0 = اشتراك دائم"
            )
            return

        if stage == "days":
            try:
                days_val = int(text)
            except ValueError:
                await update.message.reply_text("المدة لازم تكون رقم. مثال: 7 أو 30 أو 0")
                return

            if days_val <= 0:
                new_plan["days"] = None
            else:
                new_plan["days"] = days_val

            new_plan["description"] = "اشتراك مخصص تمت إضافته من لوحة التحكم."

            key_base = "plan"
            idx = 1
            while f"{key_base}_{idx}" in PLANS:
                idx += 1
            plan_key = f"{key_base}_{idx}"

            PLANS[plan_key] = {
                "title": new_plan["title"],
                "description": new_plan["description"],
                "price_stars": new_plan["price_stars"],
                "days": new_plan["days"],
            }

            await update.message.reply_text(
                "✅ تم إنشاء الخطة الجديدة:\n"
                f"- الاسم: {new_plan['title']}\n"
                f"- السعر: ⭐ {new_plan['price_stars']}\n"
                f"- المدة: {'دائم' if new_plan['days'] is None else str(new_plan['days']) + ' يوم'}\n\n"
                "اكتب /admin لو حاب تشوفها في لوحة التحكم."
            )

            context.user_data.pop("new_plan_stage", None)
            context.user_data.pop("new_plan", None)
            return


# ================= راوتر الكولباكات =================
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data

    if data.startswith("plan:"):
        await plan_screen(update, context)
    elif data.startswith("pay:"):
        await pay_handler(update, context)
    elif data == "back_main":
        await back_main(update, context)
    elif data.startswith("admin_plan:"):
        await admin_plan_screen(update, context)
    elif data.startswith("admin_price:"):
        await admin_set_price_button(update, context)
    elif data.startswith("admin_custom_price:"):
        await admin_custom_price(update, context)
    elif data.startswith("admin_custom_title:"):
        await admin_custom_title(update, context)
    elif data == "admin_back":
        await admin_back(update, context)
    elif data == "admin_add":
        await admin_add_plan_start(update, context)


# ================= تشغيل البوت =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(callback_router))

    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # رسائل فوروارد → نجيب منها ID القناة
    app.add_handler(MessageHandler(filters.FORWARDED, forward_channel_id))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler)
    )

    print("Bot is running with Stars + plans + full admin panel…")
    app.run_polling()


if __name__ == "__main__":
    main()
