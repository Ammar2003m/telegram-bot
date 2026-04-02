from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

# الدول (تقدر تعدلها لاحقاً)
countries = [
    ("US", "+1", 0.45),
    ("SA", "+966", 1.7),
    ("EG", "+20", 0.45),
    ("YE", "+967", 0.8),
]

# إضافة 5% عمولة
def add_profit(price):
    return round(price * 1.05, 2)

# إنشاء الأزرار (صفين)
def countries_keyboard():
    keyboard = []
    row = []

    for code, prefix, price in countries:
        price = add_profit(price)

        btn = InlineKeyboardButton(
            f"{code} {prefix} | {price}$",
            callback_data=f"buy_{code}"
        )

        row.append(btn)

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)

# أمر التجربة
async def buy_number(update, context):
    await update.message.reply_text(
        "اختر الدولة:",
        reply_markup=countries_keyboard()
    )

# اختيار الدولة
async def select_country(update, context):
    query = update.callback_query
    await query.answer()

    country = query.data.split("_")[1]

    await query.edit_message_text(f"اخترت الدولة: {country}")
