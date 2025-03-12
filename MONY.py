import asyncio
import logging
import datetime
import gspread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ======== Настройка токена и логирования ==========
API_TOKEN = '7987383265:AAHYOCxCVk8AeM61iFEGnzXPKFCHOXoRDjk'
logging.basicConfig(level=logging.INFO)

# ======== Инициализация бота и диспетчера ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ======== Инициализация Google Sheets ==========
# Файл credentials.json должен находиться в корневой папке проекта.
gc = gspread.service_account(filename='credentials.json')
spreadsheet = gc.open("FinancialRecords")  # Замените на имя вашей таблицы
income_sheet = spreadsheet.worksheet("Доходы")
expense_sheet = spreadsheet.worksheet("Расходы")

# ======== Глобальные переменные ==========
pending_inputs = {}         # {user_id: {"type": str, "category": str}}
records = []                # Список записей. Каждый элемент: {date, type, category, amount, comment}
registered_users = set()    # Для автоматических отчётов

# ---------------------------------------------------------------------------- #
#                        1. Главное меню (Reply-клавиатура)                    #
# ---------------------------------------------------------------------------- #
def main_menu_keyboard():
    """
    Главное меню в виде Reply-клавиатуры.
    Кнопки растягиваются почти на всю ширину экрана.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Доход"),
                KeyboardButton(text="➖ Расход")
            ],
            [
                KeyboardButton(text="💰 Баланс"),
                KeyboardButton(text="📊 Отчёты")
            ]
        ],
        resize_keyboard=True
    )

# ---------------------------------------------------------------------------- #
#                      2. Inline-клавиатуры для подменю                         #
# ---------------------------------------------------------------------------- #
def income_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Зарплата / Фриланс", callback_data="income_salary")],
            [types.InlineKeyboardButton(text="Бизнес / Инвестиции", callback_data="income_business")],
            [types.InlineKeyboardButton(text="Прочее", callback_data="income_other")]
        ]
    )

def expense_groups_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Основные расходы", callback_data="expense_group_main")],
            [types.InlineKeyboardButton(text="Личное", callback_data="expense_group_personal")],
            [types.InlineKeyboardButton(text="Дополнительные расходы", callback_data="expense_group_additional")]
        ]
    )

def expense_main_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Жильё", callback_data="expense_main_housing")],
            [types.InlineKeyboardButton(text="Продукты и еда", callback_data="expense_main_food")],
            [types.InlineKeyboardButton(text="Транспорт", callback_data="expense_main_transport")]
        ]
    )

def expense_personal_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Здоровье", callback_data="expense_personal_health")],
            [types.InlineKeyboardButton(text="Одежда и уход", callback_data="expense_personal_clothes")]
        ]
    )

def expense_additional_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="Развлечения", callback_data="expense_additional_entertainment")],
            [types.InlineKeyboardButton(text="Образование и курсы", callback_data="expense_additional_education")],
            [types.InlineKeyboardButton(text="Непредвиденные расходы", callback_data="expense_additional_unexpected")]
        ]
    )

def reports_menu_keyboard():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🗓️ Ежедневный", callback_data="report_daily")],
            [types.InlineKeyboardButton(text="📆 Недельный", callback_data="report_weekly")],
            [types.InlineKeyboardButton(text="📈 Месячный", callback_data="report_monthly")],
            [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]
    )

# ---------------------------------------------------------------------------- #
#                    3. Функция сохранения записи в Google Sheets             #
# ---------------------------------------------------------------------------- #
def save_record_to_sheet(record):
    row = [record['date'], record['category'], record['amount'], record['comment']]
    if record["type"] == "доход":
        income_sheet.append_row(row)
    else:
        expense_sheet.append_row(row)

# ---------------------------------------------------------------------------- #
#                         4. Функции формирования отчётов                     #
# ---------------------------------------------------------------------------- #
def get_current_balance():
    income_total = sum(r["amount"] for r in records if r["type"] == "доход")
    expense_total = sum(r["amount"] for r in records if r["type"] == "расход")
    return income_total - expense_total

def generate_daily_summary():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    daily = [r for r in records if r["date"].startswith(today_str)]
    incomes = [r for r in daily if r["type"] == "доход"]
    expenses = [r for r in daily if r["type"] == "расход"]
    total_income = sum(r["amount"] for r in incomes)
    total_expense = sum(r["amount"] for r in expenses)
    balance_day = total_income - total_expense
    msg = f"🗓️ Отчёт за {datetime.datetime.now().strftime('%d %B %Y')}:\n\n"
    msg += "✅ Доходы:\n"
    if incomes:
        for r in incomes:
            msg += f"- {r['category']}: {r['amount']} руб. {r['comment']}\n"
    else:
        msg += "Нет записей\n"
    msg += "\n❌ Расходы:\n"
    if expenses:
        for r in expenses:
            msg += f"- {r['category']}: {r['amount']} руб. {r['comment']}\n"
    else:
        msg += "Нет записей\n"
    msg += f"\n📌 Итого:\nДоходы: {total_income} руб.\nРасходы: {total_expense} руб.\n"
    msg += f"Баланс за день: {'+' if balance_day >= 0 else ''}{balance_day} руб."
    return msg

def generate_weekly_summary():
    now = datetime.datetime.now()
    week_ago = now - datetime.timedelta(days=7)
    weekly = []
    for r in records:
        rec_date = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        if rec_date >= week_ago:
            weekly.append(r)
    total_income = sum(r["amount"] for r in weekly if r["type"] == "доход")
    total_expense = sum(r["amount"] for r in weekly if r["type"] == "расход")
    balance_week = total_income - total_expense
    msg = f"📆 Недельный отчёт ({(now - datetime.timedelta(days=7)).strftime('%d.%m')}–{now.strftime('%d.%m')}):\n\n"
    msg += f"✅ Общий доход: {total_income} руб.\n"
    msg += f"❌ Общий расход: {total_expense} руб.\n\n"
    msg += f"💰 Итого за неделю: {'+' if balance_week >= 0 else ''}{balance_week} руб."
    return msg

def generate_monthly_report():
    now = datetime.datetime.now()
    if now.month == 1:
        prev_month = 12
        year = now.year - 1
    else:
        prev_month = now.month - 1
        year = now.year
    monthly_expenses = []
    for r in records:
        rec_date = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        if r["type"] == "расход" and rec_date.year == year and rec_date.month == prev_month:
            monthly_expenses.append(r)
    if not monthly_expenses:
        return f"Нет данных за {year}-{prev_month:02d}"
    total_expense = sum(r["amount"] for r in monthly_expenses)
    category_sums = {}
    for r in monthly_expenses:
        cat = r["category"]
        category_sums[cat] = category_sums.get(cat, 0) + r["amount"]
    report_lines = [f"📊 Расходы за {datetime.date(year, prev_month, 1).strftime('%B')}:"]
    for cat, amount in category_sums.items():
        percentage = (amount / total_expense) * 100
        bar = "█" * int(percentage / 3.5)  # Пример: 35% ≈ 10 символов
        report_lines.append(f"{cat}: {bar} {percentage:.0f}%")
    report_lines.append(f"\n💸 Итого расходов: {total_expense} руб.")
    monthly_incomes = []
    for r in records:
        rec_date = datetime.datetime.strptime(r["date"], "%Y-%m-%d %H:%M:%S")
        if r["type"] == "доход" and rec_date.year == year and rec_date.month == prev_month:
            monthly_incomes.append(r)
    total_income = sum(r["amount"] for r in monthly_incomes)
    report_lines.append(f"💰 Общие доходы: {total_income} руб.")
    report_lines.append(f"💳 Итоговый баланс месяца: {'+' if (total_income - total_expense) >= 0 else ''}{total_income - total_expense} руб.")
    return "\n".join(report_lines)

# ---------------------------------------------------------------------------- #
#                5. Обработчики команд и сообщений (Reply и Inline)            #
# ---------------------------------------------------------------------------- #
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    registered_users.add(message.from_user.id)
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu_keyboard())

@dp.message(lambda m: m.text == "➕ Доход")
async def choose_income_handler(message: types.Message):
    await message.answer("Выберите категорию дохода:", reply_markup=income_keyboard())

@dp.message(lambda m: m.text == "➖ Расход")
async def choose_expense_handler(message: types.Message):
    await message.answer("Выберите группу расходов:", reply_markup=expense_groups_keyboard())

@dp.message(lambda m: m.text == "💰 Баланс")
async def show_balance_handler(message: types.Message):
    balance = get_current_balance()
    await message.answer(f"Твой текущий баланс: {'+' if balance >= 0 else ''}{balance} руб.", reply_markup=main_menu_keyboard())

@dp.message(lambda m: m.text == "📊 Отчёты")
async def choose_reports_handler(message: types.Message):
    await message.answer("Выберите тип отчёта:", reply_markup=reports_menu_keyboard())

@dp.callback_query(lambda c: c.data.startswith("income_"))
async def process_income_category(callback: types.CallbackQuery):
    key = callback.data.split("_")[1]
    if key == "salary":
        chosen = "Зарплата / Фриланс"
    elif key == "business":
        chosen = "Бизнес / Инвестиции"
    elif key == "other":
        chosen = "Прочее"
    else:
        chosen = "Неизвестная категория"
    pending_inputs[callback.from_user.id] = {"type": "доход", "category": chosen}
    await callback.answer()
    await bot.send_message(callback.from_user.id,
                           f"Вы выбрали: {chosen}\nВведите сумму и опциональный комментарий (например: '500 кафе с друзьями')")

@dp.callback_query(lambda c: c.data.startswith("expense_group_"))
async def process_expense_group(callback: types.CallbackQuery):
    group = callback.data.split("_")[2]
    await callback.answer()
    if group == "main":
        await bot.send_message(callback.from_user.id, "Выберите категорию основных расходов:", reply_markup=expense_main_keyboard())
    elif group == "personal":
        await bot.send_message(callback.from_user.id, "Выберите категорию личных расходов:", reply_markup=expense_personal_keyboard())
    elif group == "additional":
        await bot.send_message(callback.from_user.id, "Выберите категорию дополнительных расходов:", reply_markup=expense_additional_keyboard())
    else:
        await bot.send_message(callback.from_user.id, "Неизвестная группа расходов.")

@dp.callback_query(lambda c: c.data.startswith("expense_main_") or c.data.startswith("expense_personal_") or c.data.startswith("expense_additional_"))
async def process_expense_category(callback: types.CallbackQuery):
    data = callback.data
    chosen = None
    if data.startswith("expense_main_"):
        sub = data.split("_")[2]
        if sub == "housing":
            chosen = "Жильё"
        elif sub == "food":
            chosen = "Продукты и еда"
        elif sub == "transport":
            chosen = "Транспорт"
    elif data.startswith("expense_personal_"):
        sub = data.split("_")[2]
        if sub == "health":
            chosen = "Здоровье"
        elif sub == "clothes":
            chosen = "Одежда и уход"
    elif data.startswith("expense_additional_"):
        sub = data.split("_")[2]
        if sub == "entertainment":
            chosen = "Развлечения"
        elif sub == "education":
            chosen = "Образование и курсы"
        elif sub == "unexpected":
            chosen = "Непредвиденные расходы"
    if not chosen:
        chosen = "Неизвестная категория"
    pending_inputs[callback.from_user.id] = {"type": "расход", "category": chosen}
    await callback.answer()
    await bot.send_message(callback.from_user.id,
                           f"Вы выбрали: {chosen}\nВведите сумму и опциональный комментарий")

@dp.callback_query(lambda c: c.data == "report_daily")
async def process_report_daily(callback: types.CallbackQuery):
    await callback.answer()
    report = generate_daily_summary()
    await bot.send_message(callback.from_user.id, report)
    await bot.send_message(callback.from_user.id, "Главное меню:", reply_markup=main_menu_keyboard())

@dp.callback_query(lambda c: c.data == "report_weekly")
async def process_report_weekly(callback: types.CallbackQuery):
    await callback.answer()
    report = generate_weekly_summary()
    await bot.send_message(callback.from_user.id, report)
    await bot.send_message(callback.from_user.id, "Главное меню:", reply_markup=main_menu_keyboard())

@dp.callback_query(lambda c: c.data == "report_monthly")
async def process_report_monthly(callback: types.CallbackQuery):
    await callback.answer()
    report = generate_monthly_report()
    await bot.send_message(callback.from_user.id, report)
    await bot.send_message(callback.from_user.id, "Главное меню:", reply_markup=main_menu_keyboard())

@dp.message(lambda message: message.from_user.id in pending_inputs)
async def process_manual_input(message: types.Message):
    user_id = message.from_user.id
    pending = pending_inputs.get(user_id)
    if not pending:
        return
    text = message.text.strip()
    parts = text.split(maxsplit=1)
    if not parts:
        await message.reply("Пожалуйста, введите сумму и комментарий.")
        return
    try:
        amount = float(parts[0])
    except ValueError:
        await message.reply("Неверный формат суммы. Введите число в начале сообщения.")
        return
    comment = parts[1] if len(parts) > 1 else ""
    record = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": pending["type"],
        "category": pending["category"],
        "amount": amount,
        "comment": comment
    }
    records.append(record)
    await asyncio.to_thread(save_record_to_sheet, record)
    del pending_inputs[user_id]
    await message.reply(
        f"Запись сохранена:\nДата: {record['date']}\nТип: {record['type']}\nКатегория: {record['category']}\n"
        f"Сумма: {record['amount']}\nКомментарий: {record['comment']}"
    )
    await bot.send_message(message.from_user.id, "Главное меню:", reply_markup=main_menu_keyboard())

# ---------------------------------------------------------------------------- #
#                 6. Фоновые задачи для автоматических отчётов                 #
# ---------------------------------------------------------------------------- #
async def daily_summary_task():
    while True:
        now = datetime.datetime.now()
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        delay = (target - now).total_seconds()
        await asyncio.sleep(delay)
        report = generate_daily_summary()
        for user_id in registered_users:
            try:
                await bot.send_message(user_id, report)
            except Exception as e:
                logging.error(f"Ошибка отправки ежедневной сводки пользователю {user_id}: {e}")
        await asyncio.sleep(60)

async def weekly_summary_task():
    while True:
        now = datetime.datetime.now()
        days_ahead = 6 - now.weekday()
        target = now.replace(hour=20, minute=0, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
        if now >= target:
            target += datetime.timedelta(weeks=1)
        delay = (target - now).total_seconds()
        await asyncio.sleep(delay)
        report = generate_weekly_summary()
        for user_id in registered_users:
            try:
                await bot.send_message(user_id, report)
            except Exception as e:
                logging.error(f"Ошибка отправки недельного отчёта пользователю {user_id}: {e}")
        await asyncio.sleep(60)

async def monthly_summary_task():
    while True:
        now = datetime.datetime.now()
        if now.day == 1 and now.hour < 10:
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        else:
            if now.month == 12:
                target = datetime.datetime(now.year + 1, 1, 1, 10, 0, 0)
            else:
                target = datetime.datetime(now.year, now.month + 1, 1, 10, 0, 0)
        delay = (target - now).total_seconds()
        await asyncio.sleep(delay)
        report = generate_monthly_report()
        for user_id in registered_users:
            try:
                await bot.send_message(user_id, report)
            except Exception as e:
                logging.error(f"Ошибка отправки месячного отчёта пользователю {user_id}: {e}")
        await asyncio.sleep(60)

# ---------------------------------------------------------------------------- #
#                             Основная функция                               #
# ---------------------------------------------------------------------------- #
async def main():
    asyncio.create_task(daily_summary_task())
    asyncio.create_task(weekly_summary_task())
    asyncio.create_task(monthly_summary_task())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
