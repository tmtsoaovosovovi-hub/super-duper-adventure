import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- КОНФИГ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
ADMINS = [8119723042, 8377754197, 8330987864] 
SUPPORT_LINK = "https://t.me/BOSSI2026"
CRYPTO_BOT_USERNAME = "@CryptoBot" # Для вывода

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('boss_crypto_v25.db')
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        res = cursor.fetchone() if fetchone else cursor.fetchall() if fetchall else None
        if commit: conn.commit()
        return res
    finally: conn.close()

def init_db():
    db_query('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, tariff TEXT, phone TEXT, price REAL)', commit=True)
    for adm in ADMINS:
        db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (adm,), commit=True)

# --- СОСТОЯНИЯ ---
class FSMApp(StatesGroup):
    platform = State(); tariff = State(); phone = State()

class FSMWithdraw(StatesGroup):
    amount = State(); wallet = State()

# --- ГЛАВНОЕ МЕНЮ (ИНЛАЙН) ---
def get_main_inline(uid):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal = res[0] if res else 0
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    kb = [
        [InlineKeyboardButton(text=f"💰 Баланс: {bal}$", callback_data="none")],
        [InlineKeyboardButton(text="📱 Сдать номер", callback_data="app_start"), InlineKeyboardButton(text="💸 Вывод (CryptoBot)", callback_data="app_withdraw")],
        [InlineKeyboardButton(text="⏳ Очередь", callback_data="q_start"), InlineKeyboardButton(text="👨‍💻 Поддержка", url=SUPPORT_LINK)]
    ]
    if uid in adms:
        kb.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="adm_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    await message.answer("🏦 <b>Добро пожаловать в сервис!</b>\nВсе выплаты производятся через <b>Crypto Bot</b>.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=get_main_inline(message.from_user.id))

# --- СДАЧА НОМЕРА ---
@dp.callback_query(F.data == "app_start")
async def app_1(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВК", callback_data="st_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="st_ВЦ")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await call.message.edit_text("Выберите платформу для сдачи:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("st_"))
async def app_2(call: CallbackQuery, state: FSMContext):
    p = call.data.split("_")[1]; await state.update_data(platform=p)
    if p == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2$/15мин", callback_data="tr_2.0")],
            [InlineKeyboardButton(text="1.3$/0мин", callback_data="tr_1.3")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="app_start")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3$/20мин", callback_data="tr_3.0")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="app_start")]
        ])
    await call.message.edit_text(f"Выберите тариф для <b>{p}</b>:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("tr_"))
async def app_3(call: CallbackQuery, state: FSMContext):
    price = float(call.data.split("_")[1])
    await state.update_data(price=price)
    await call.message.edit_text("📱 <b>Введите номер телефона:</b>\n(Например: +79991234567)")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def app_4(message: Message, state: FSMContext):
    d = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone, price) VALUES (?,?,?,?,?)', 
             (message.from_user.id, d['platform'], f"{d['price']}$", message.text, d['price']), commit=True)
    await message.answer(f"✅ Номер {message.text} добавлен в очередь!", reply_markup=get_main_inline(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ И АВТО-ЗАЧИСЛЕНИЕ ---
@dp.callback_query(F.data == "q_start")
async def q_1(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очередь ВК", callback_data="v_ВК"), InlineKeyboardButton(text="Очередь ВЦ", callback_data="v_ВЦ")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await call.message.edit_text("Какую очередь открыть?", reply_markup=kb)

@dp.callback_query(F.data.startswith("v_"))
async def q_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.", reply_markup=get_main_inline(call.from_user.id))
    await call.message.delete()
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять в работу", callback_data=f"take_{r[0]}")]])
        await call.message.answer(f"📦 Заявка #{r[0]}\nТариф: {r[1]}\nНомер: <code>{r[2]}</code>", reply_markup=kb)

@dp.callback_query(F.data.startswith("take_"))
async def take_logic(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, price, id FROM apps WHERE id=?', (aid,), fetchone=True)
    if not res: return await call.answer("Уже обработано.")
    uid, phone, price, real_id = res
    await state.update_data(target_user=uid, target_app_id=real_id, price=price)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить (Оплата зачислится)", callback_data="r_ok")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data="r_no")]
    ])
    await call.message.answer(f"📱 Работа с номером <code>{phone}</code>\nЗа подтверждение юзер получит <b>{price}$</b>", reply_markup=kb)

@dp.callback_query(F.data == "r_ok")
async def r_ok(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # АВТОМАТИЧЕСКИЙ ПЛЮС В БАЗУ
    db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (data['price'], data['target_user']), commit=True)
    db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    
    await bot.send_message(data['target_user'], f"✅ <b>Номер успешно принят!</b>\nНа ваш баланс зачислено: <b>{data['price']}$</b>\nВывести можно через раздел 'Вывод'.")
    await call.message.edit_text(f"✅ Готово! Юзеру зачислено {data['price']}$")
    await state.clear()

# --- ВЫВОД ЧЕРЕЗ КРИПТОБОТ ---
@dp.callback_query(F.data == "app_withdraw")
async def wd_1(call: CallbackQuery, state: FSMContext):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (call.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    if bal <= 0: return await call.answer("Недостаточно средств для вывода (0$).", show_alert=True)
    await call.message.edit_text(f"💰 Ваш баланс: {bal}$.\nВведите сумму для вывода в $:")
    await state.set_state(FSMWithdraw.amount)

@dp.message(FSMWithdraw.amount)
async def wd_2(message: Message, state: FSMContext):
    try:
        amt = float(message.text)
        res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
        if amt > res[0]: return await message.answer("Сумма превышает ваш баланс!")
        await state.update_data(amt=amt)
        await message.answer(f"Для получения выплаты пришлите ваш ID в {CRYPTO_BOT_USERNAME} или адрес кошелька:")
        await state.set_state(FSMWithdraw.wallet)
    except:
        await message.answer("Введите число!")

@dp.message(FSMWithdraw.wallet)
async def wd_3(message: Message, state: FSMContext):
    d = await state.get_data()
    # Снимаем баланс сразу (Hold)
    db_query('UPDATE users SET balance = balance - ? WHERE user_id = ?', (d['amt'], message.from_user.id), commit=True)
    
    # Уведомляем админов
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Выплачено", callback_data="wd_done")]])
    for adm in ADMINS:
        try:
            await bot.send_message(adm, f"💎 <b>ВЫВОД CRYPTO BOT</b>\nЮзер: <code>{message.from_user.id}</code>\nСумма: <b>{d['amt']}$</b>\nРеквизиты: <code>{message.text}</code>\n\n<i>Отправьте чек в CryptoBot и нажмите кнопку ниже.</i>", reply_markup=kb)
        except: pass
    
    await message.answer("✅ <b>Заявка принята!</b>\nАдмин отправит вам чек в Crypto Bot в ближайшее время.", reply_markup=get_main_inline(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "wd_done")
async def wd_done(call: CallbackQuery):
    await call.message.edit_text(call.message.text + "\n\n✅ <b>СТАТУС: ВЫПЛАЧЕНО</b>")

@dp.callback_query(F.data == "back_main")
async def b_m(call: CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=get_main_inline(call.from_user.id))

# --- ЗАПУСК ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    print("Бот запущен на токене 8529283906")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
