
import os
import sqlite3
import logging
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(value)
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}
DB_PATH = os.getenv("DB_PATH", "orinboy_orders.db")

MENU = {
    "classic": {"uz": "Klassik hotdog", "ru": "Классический хот-дог", "price": 28000},
    "cheese": {"uz": "Pishloqli hotdog", "ru": "Хот-дог с сыром", "price": 32000},
    "double": {"uz": "Double hotdog", "ru": "Двойной хот-дог", "price": 40000},
    "fries": {"uz": "Fri kartoshka", "ru": "Картофель фри", "price": 18000},
    "cola": {"uz": "Cola 0.5 l", "ru": "Кола 0,5 л", "price": 12000},
}

TEXT = {
    "uz": {
        "home": "Kerakli bo‘limni tanlang:",
        "menu": "🌭 Menyu",
        "empty": "Savatingiz bo‘sh.",
        "added": "Savatga qo‘shildi ✅",
        "cart": "🛒 Savatingiz",
        "checkout": "Buyurtma berish",
        "name": "Ism-familiyangizni yozing:",
        "phone": "Telefon raqamingizni yuboring yoki yozing:",
        "address": "Yetkazib berish manzilini to‘liq yozing:",
        "payment": "To‘lov turini tanlang:",
        "cash": "💵 Naqd pul",
        "card": "💳 Kuryerga karta",
        "sent": "Buyurtmangiz adminga yuborildi! ✅",
        "cancelled": "Buyurtma bekor qilindi.",
        "delivery": "🚚 Yetkazib berish narxi kuryer bilan kelishiladi.",
        "total": "Jami",
        "bad": "Ma’lumotni qaytadan yuboring.",
    },
    "ru": {
        "home": "Выберите нужный раздел:",
        "menu": "🌭 Меню",
        "empty": "Корзина пуста.",
        "added": "Добавлено в корзину ✅",
        "cart": "🛒 Ваша корзина",
        "checkout": "Оформить заказ",
        "name": "Напишите ваше имя и фамилию:",
        "phone": "Отправьте или напишите номер телефона:",
        "address": "Напишите полный адрес доставки:",
        "payment": "Выберите способ оплаты:",
        "cash": "💵 Наличные",
        "card": "💳 Картой курьеру",
        "sent": "Ваш заказ отправлен администратору! ✅",
        "cancelled": "Заказ отменён.",
        "delivery": "🚚 Стоимость доставки согласуется с курьером.",
        "total": "Итого",
        "bad": "Пожалуйста, отправьте данные ещё раз.",
    },
}


def tr(lang, key):
    return TEXT.get(lang, TEXT["uz"]).get(key, key)


def money(amount):
    return f"{amount:,}".replace(",", " ") + " so‘m"


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                payment TEXT NOT NULL,
                items TEXT NOT NULL,
                total INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'Yangi',
                created_at TEXT NOT NULL
            )
        """)


def lang_of(context):
    return context.user_data.get("lang", "uz")


def home_keyboard(lang):
    menu_label = "🔥 Menyu" if lang == "uz" else "🔥 Меню"
    cart_label = "🛒 Savat" if lang == "uz" else "🛒 Корзина"
    language_label = "🌐 Tilni almashtirish" if lang == "uz" else "🌐 Сменить язык"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(menu_label, callback_data="menu")],
        [InlineKeyboardButton(cart_label, callback_data="cart")],
        [InlineKeyboardButton(language_label, callback_data="language")],
    ])


def menu_keyboard(lang):
    rows = []

    for key, item in MENU.items():
        rows.append([
            InlineKeyboardButton(
                f"{item[lang]} — {money(item['price'])}",
                callback_data=f"add:{key}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "🛒 Savat" if lang == "uz" else "🛒 Корзина",
            callback_data="cart",
        )
    ])
    rows.append([
        InlineKeyboardButton(
            "⬅️ Orqaga" if lang == "uz" else "⬅️ Назад",
            callback_data="home",
        )
    ])
    return InlineKeyboardMarkup(rows)


def cart_details(context, lang):
    cart = context.user_data.get("cart", {})
    if not cart:
        return tr(lang, "empty"), 0

    lines = []
    total = 0

    for key, qty in cart.items():
        item = MENU.get(key)
        if item and qty > 0:
            subtotal = item["price"] * qty
            total += subtotal
            lines.append(
                f"• {item[lang]} × {qty} — {money(subtotal)}"
            )

    lines.append("")
    lines.append(tr(lang, "delivery"))
    lines.append(f"*{tr(lang, 'total')}: {money(total)}*")
    return "\n".join(lines), total


def cart_keyboard(lang, has_items):
    rows = []

    if has_items:
        rows.append([
            InlineKeyboardButton(
                tr(lang, "checkout"),
                callback_data="checkout",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                "🗑 Savatni bo‘shatish" if lang == "uz"
                else "🗑 Очистить корзину",
                callback_data="clear",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "⬅️ Orqaga" if lang == "uz" else "⬅️ Назад",
            callback_data="home",
        )
    ])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("cart", {})

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="lang:uz")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru")],
    ])

    await update.message.reply_text(
        "🌭 Orinboy Hotdog\nTilni tanlang / Выберите язык:",
        reply_markup=keyboard,
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    lang = lang_of(context)
    context.user_data.setdefault("cart", {})

    if data.startswith("lang:"):
        context.user_data["lang"] = data.split(":")[1]
        lang = lang_of(context)
        await query.edit_message_text(
            tr(lang, "home"),
            reply_markup=home_keyboard(lang),
        )
        return

    if data == "language":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="lang:uz")],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang:ru")],
        ])
        await query.edit_message_text(
            "Tilni tanlang / Выберите язык:",
            reply_markup=keyboard,
        )

    elif data == "home":
        await query.edit_message_text(
            tr(lang, "home"),
            reply_markup=home_keyboard(lang),
        )

    elif data == "menu":
        await query.edit_message_text(
            tr(lang, "menu"),
            reply_markup=menu_keyboard(lang),
        )

    elif data.startswith("add:"):
        key = data.split(":", 1)[1]
        if key in MENU:
            cart = context.user_data["cart"]
            cart[key] = cart.get(key, 0) + 1
            await query.answer(tr(lang, "added"))
            await query.edit_message_reply_markup(
                reply_markup=menu_keyboard(lang)
            )

    elif data == "cart":
        text, total = cart_details(context, lang)
        await query.edit_message_text(
            text,
            reply_markup=cart_keyboard(lang, total > 0),
            parse_mode="Markdown",
        )

    elif data == "clear":
        context.user_data["cart"] = {}
        await query.edit_message_text(
            tr(lang, "empty"),
            reply_markup=cart_keyboard(lang, False),
        )

    elif data == "checkout":
        if not context.user_data.get("cart"):
            await query.edit_message_text(tr(lang, "empty"))
            return

        context.user_data["order_data"] = {}
        context.user_data["checkout_step"] = "name"
        await query.edit_message_text(tr(lang, "name"))

    elif data.startswith("pay:"):
        await finish_order(update, context, data.split(":", 1)[1])


async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("checkout_step")
    if not step:
        return

    lang = lang_of(context)
    msg = update.message
    value = (msg.text or "").strip() if msg.text else ""

    if step == "phone" and msg.contact:
        value = msg.contact.phone_number

    if not value:
        await msg.reply_text(tr(lang, "bad"))
        return

    order_data = context.user_data.setdefault("order_data", {})

    if step == "name":
        order_data["name"] = value[:120]
        context.user_data["checkout_step"] = "phone"

        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(
                "📞 Telefonni yuborish" if lang == "uz"
                else "📞 Отправить телефон",
                request_contact=True,
            )]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await msg.reply_text(
            tr(lang, "phone"),
            reply_markup=keyboard,
        )

    elif step == "phone":
        order_data["phone"] = value[:40]
        context.user_data["checkout_step"] = "address"
        await msg.reply_text(
            tr(lang, "address"),
            reply_markup=ReplyKeyboardRemove(),
        )

    elif step == "address":
        order_data["address"] = value[:500]
        context.user_data["checkout_step"] = "payment"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                tr(lang, "cash"), callback_data="pay:cash"
            )],
            [InlineKeyboardButton(
                tr(lang, "card"), callback_data="pay:card"
            )],
        ])
        await msg.reply_text(
            tr(lang, "payment"),
            reply_markup=ReplyKeyboardRemove(),
        )
        await msg.reply_text(
            tr(lang, "payment"),
            reply_markup=keyboard,
        )


async def finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE, payment):
    query = update.callback_query
    lang = lang_of(context)

    if context.user_data.get("checkout_step") != "payment":
        await query.edit_message_text(tr(lang, "bad"))
        return

    cart = context.user_data.get("cart", {})
    order_data = context.user_data.get("order_data", {})

    if not cart:
        await query.edit_message_text(tr(lang, "empty"))
        return

    items = []
    total = 0

    for key, qty in cart.items():
        item = MENU.get(key)
        if item and qty > 0:
            items.append(f"{item['uz']} x{qty}")
            total += item["price"] * qty

    payment_label = (
        tr(lang, "cash") if payment == "cash" else tr(lang, "card")
    )
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("""
            INSERT INTO orders
            (user_id, customer_name, phone, address, payment,
             items, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            update.effective_user.id,
            order_data.get("name", ""),
            order_data.get("phone", ""),
            order_data.get("address", ""),
            payment_label,
            "; ".join(items),
            total,
            "Yangi",
            created_at,
        ))
        order_id = cur.lastrowid

    summary = (
        f"🆕 Yangi buyurtma #{order_id}\n"
        f"👤 {order_data.get('name', '')}\n"
        f"📞 {order_data.get('phone', '')}\n"
        f"📍 {order_data.get('address', '')}\n"
        f"🍔 {'; '.join(items)}\n"
        f"💳 {payment_label}\n"
        f"🚚 Yetkazib berish: kuryer bilan kelishiladi\n"
        f"💰 Jami: {money(total)}\n"
        f"🕒 {created_at}"
    )

    admin_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "👨‍🍳 Tayyorlanmoqda",
            callback_data=f"status:{order_id}:Tayyorlanmoqda",
        )],
        [InlineKeyboardButton(
            "🛵 Kuryerga topshirildi",
            callback_data=f"status:{order_id}:Kuryerga topshirildi",
        )],
        [InlineKeyboardButton(
            "✅ Yetkazib berildi",
            callback_data=f"status:{order_id}:Yetkazib berildi",
        )],
    ])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=summary,
                reply_markup=admin_keyboard,
            )
        except Exception:
            logging.exception("Adminga buyurtma yuborilmadi")

    context.user_data["cart"] = {}
    context.user_data.pop("order_data", None)
    context.user_data.pop("checkout_step", None)

    await query.edit_message_text(
        tr(lang, "sent"),
        reply_markup=home_keyboard(lang),
    )


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.answer("Bu tugma faqat admin uchun.", show_alert=True)
        return

    _, order_id, status = query.data.split(":", 2)

    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT user_id FROM orders WHERE id = ?",
            (int(order_id),),
        ).fetchone()

        con.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, int(order_id)),
        )

    if row:
        try:
            await context.bot.send_message(
                chat_id=row[0],
                text=f"📦 Buyurtma #{order_id} holati: {status}",
            )
        except Exception:
            logging.exception("Mijozga status yuborilmadi")

    await query.edit_message_reply_markup(reply_markup=None)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = lang_of(context)
    context.user_data.pop("checkout_step", None)
    context.user_data.pop("order_data", None)

    await update.message.reply_text(
        tr(lang, "cancelled"),
        reply_markup=ReplyKeyboardRemove(),
    )


async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return

    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute("""
            SELECT id, customer_name, total, status, created_at
            FROM orders ORDER BY id DESC LIMIT 20
        """).fetchall()

    if not rows:
        await update.message.reply_text("Hozircha buyurtmalar yo‘q.")
        return

    lines = ["📋 Oxirgi buyurtmalar:"]
    for row in rows:
        lines.append(
            f"#{row[0]} | {row[1]} | {money(row[2])} | "
            f"{row[3]} | {row[4]}"
        )

    await update.message.reply_text("\n".join(lines))


async def post_init(application: Application):
    init_db()
    logging.info("Orinboy Hotdog bot ishga tushdi.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi. Render Environment Variables ichiga qo‘shing."
        )

    if not ADMIN_IDS:
        logging.warning("ADMIN_IDS kiritilmagan.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        # Telegram API sekin javob bersa, kutish vaqtini oshiramiz.
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(40)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("orders", orders))
    app.add_handler(CallbackQueryHandler(
        admin_status, pattern=r"^status:"
    ))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.CONTACT, messages
    ))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
