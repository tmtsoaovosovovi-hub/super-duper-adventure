import asyncio
import sqlite3
import logging
import re
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
TOKEN = '538538:AAjGN8rPhv0629d7rPQWIbp10P8KIbRUKmB'
ADMINS = [8119723042, 8377754197, 8330987864] 
SUPPORT_LINK = "https://t.me/BOSSI2026"
CHANNEL_ID = -1003717021572 
CHANNEL_URL = "https://t.me/ik_126_channel"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('v23_auto_pay.db')
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
class FSMAdmin(StatesGroup):
    wait_qr = State(); edit_bal = State(); broadcast = State()

class FSMApp(StatesGroup):
    platform = State(); tariff = State(); phone = State()

class FSMWithdraw(StatesGroup):
    amount = State(); wallet = State()

# --- МЕНЮ ---
def get_main_inline(uid):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal = res[0] if res else 0
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    kb = [
        [InlineKeyboardButton(text=f"💰 Баланс: {bal}$", callback_data="none")],
        [InlineKeyboardButton(text="📱 Сдать номер", callback_data="app_start"), InlineKeyboardButton(text="💸 Вывод", callback_data="app_withdraw")],
        [InlineKeyboardButton(text="⏳ Очередь", callback_data="q_start"), InlineKeyboardButton(text="👨‍💻 Поддержка", url=SUPPORT_LINK)]
    ]
    if uid in adms: kb.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="adm_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- СТАРТ ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    await message.answer("<b>Добро пожаловать!</b>\nИспользуйте меню под сообщением.", reply_markup=get_main_inline(message.from_user.id))
    await message.answer("Клавиатура скрыта.", reply_markup=ReplyKeyboardRemove())

# --- ЛОГИКА СДАЧИ НОМЕРА (С ЦЕНАМИ) ---
@dp.callback_query(F.data == "app_start")
async def app_1(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВК", callback_data="st_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="st_ВЦ")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await call.message.edit_text("Выберите платформу:", reply_markup=kb)
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
    await call.message.edit_text(f"Выберите тариф для {p}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("tr_"))
async def app_3(call: CallbackQuery, state: FSMContext):
    price = float(call.data.split("_")[1])
    await state.update_data(price=price)
    await call.message.edit_text("Введите номер телефона:")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def app_4(message: Message, state: FSMContext):
    d = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone, price) VALUES (?,?,?,?,?)', 
             (message.from_user.id, d['platform'], f"{d['price']}$", message.text, d['price']), commit=True)
    await message.answer("✅ Номер в очереди!", reply_markup=get_main_inline(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ И АВТО-ОПЛАТА ---
@dp.callback_query(F.data.startswith("v_"))
async def q_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    if not rows: return await call.message.edit_text("Пусто.", reply_markup=get_main_inline(call.from_user.id))
    await call.message.delete()
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять", callback_data=f"take_{r[0]}")]])
        await call.message.answer(f"Заявка #{r[0]}\nТариф: {r[1]}\nНомер: {r[2]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("take_"))
async def take(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, price, id FROM apps WHERE id=?', (aid,), fetchone=True)
    uid, phone, price, real_id = res
    await state.update_data(target_user=uid, target_app_id=real_id, price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить и Оплатить", callback_data="r_ok")]])
    await call.message.answer(f"Работа с {phone}. Цена: {price}$", reply_markup=kb)

@dp.callback_query(F.data == "r_ok")
async def r_ok(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    # Начисляем баланс
    db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (data['price'], data['target_user']), commit=True)
    # Удаляем заявку
    db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    
    await bot.send_message(data['target_user'], f"✅ <b>Номер принят!</b>\nНа ваш баланс начислено <b>{data['price']}$</b>")
    await call.message.edit_text(f"✅ Готово. Юзеру зачислено {data['price']}$")
    await state.clear()

# --- ВЫВОД СРЕДСТВ ---
@dp.callback_query(F.data == "app_withdraw")
async def withdraw_1(call: CallbackQuery, state: FSMContext):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (call.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    if bal < 1: return await call.answer("Минимальный вывод от 1$", show_alert=True)
    await call.message.edit_text(f"Твой баланс: {bal}$.\nВведите сумму для вывода:")
    await state.set_state(FSMWithdraw.amount)

@dp.message(FSMWithdraw.amount)
async def withdraw_2(message: Message, state: FSMContext):
    await state.update_data(amt=message.text)
    await message.answer("Введите ваши реквизиты (Карта/Крипта):")
    await state.set_state(FSMWithdraw.wallet)

@dp.message(FSMWithdraw.wallet)
async def withdraw_3(message: Message, state: FSMContext):
    data = await state.get_data()
    # Уведомляем админов
    for adm in ADMINS:
        try: await bot.send_message(adm, f"🚨 <b>Заявка на вывод!</b>\nЮзер: {message.from_user.id}\nСумма: {data['amt']}$\nРеквизиты: {message.text}")
        except: pass
    await message.answer("✅ Заявка отправлена админаm! Ожидайте выплату.", reply_markup=get_main_inline(message.from_user.id))
    await state.clear()

# --- КНОПКИ НАВИГАЦИИ ---
@dp.callback_query(F.data == "q_start")
async def q_1(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ВК", callback_data="v_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="v_ВЦ")]])
    await call.message.edit_text("Очереди:", reply_markup=kb)

@dp.callback_query(F.data == "back_main")
async def b_m(call: CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=get_main_inline(call.from_user.id))

async def main():
    init_db(); logging.basicConfig(level=logging.INFO); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
