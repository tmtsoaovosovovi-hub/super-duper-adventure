import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

# --- КОНФИГ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
OWNER_ID = 8119723042

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('bot_final.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = None
    if fetchone: res = cursor.fetchone()
    if fetchall: res = cursor.fetchall()
    if commit: conn.commit()
    conn.close()
    return res

def init_db():
    queries = [
        'CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)',
        'CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)',
        'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)',
        'CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, tariff TEXT, phone TEXT, status TEXT)'
    ]
    for q in queries: db_query(q, commit=True)
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('photo', 'NONE'), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('chan_id', '-1000000000'), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('chan_url', 'https://t.me/+El8vWu80EDFjYjk6'), commit=True)

# --- СОСТОЯНИЯ ---
class FSMSettings(StatesGroup):
    photo = State()
    chan_id = State()
    add_adm = State()
    broadcast = State()
    edit_balance_id = State()
    edit_balance_sum = State()

class FSMApp(StatesGroup):
    platform = State()
    tariff = State()
    phone = State()

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    bal = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    balance_text = f"💰 Баланс: {bal[0] if bal else 0} руб."
    
    kb = [
        [KeyboardButton(text=balance_text)],
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in admins: kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ХЕНДЛЕРЫ СТАРТА ---
@router.message(CommandStart())
async def start(message: Message):
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    cap = "<b>Привет!</b>\nСдавай номера и зарабатывай деньги."
    
    try:
        if photo == "NONE":
            await message.answer(cap, reply_markup=main_kb(message.from_user.id))
        else:
            await message.answer_photo(photo=photo, caption=cap, reply_markup=main_kb(message.from_user.id))
    except TelegramBadRequest:
        await message.answer(cap, reply_markup=main_kb(message.from_user.id))

# --- ЛОГИКА СДАЧИ НОМЕРА С ТАРИФАМИ ---
@router.message(F.text == "📱 Сдать номер")
async def app_start(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="ВК", callback_data="p_ВК"),
        InlineKeyboardButton(text="ВЦ", callback_data="p_ВЦ")
    ]])
    await message.answer("Выберите платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@router.callback_query(F.data.startswith("p_"))
async def app_plat(call: CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[1]
    await state.update_data(platform=plat)
    
    if plat == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2/15м", callback_data="t_2/15м")],
            [InlineKeyboardButton(text="1.3/0м", callback_data="t_1.3/0м")]
        ])
    else: # ВЦ
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3/20", callback_data="t_3/20")]
        ])
    
    await call.message.edit_text(f"Выберите тариф для {plat}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@router.callback_query(F.data.startswith("t_"))
async def app_tariff(call: CallbackQuery, state: FSMContext):
    tariff = call.data.split("_")[1]
    await state.update_data(tariff=tariff)
    await call.message.edit_text(f"Введите номер телефона:")
    await state.set_state(FSMApp.phone)

@router.message(FSMApp.phone)
async def app_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone, status) VALUES (?, ?, ?, ?, ?)', 
            (message.from_user.id, data['platform'], data['tariff'], message.text, "Ожидание"), commit=True)
    
    await message.answer(f"✅ Заявка {data['platform']} ({data['tariff']}) принята в очередь!")
    # Уведомление админам
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    for a in adms:
        try:
            await bot.send_message(a, f"🔔 <b>Новая заявка!</b>\nЮзер: <code>{message.from_user.id}</code>\nПлатформа: {data['platform']}\nТариф: {data['tariff']}\nНомер: {message.text}")
        except: pass
    await state.clear()

# --- АДМИНКА: ИЗМЕНЕНИЕ БАЛАНСА ---
@router.message(F.text == "⚙️ Админка")
async def adm_main(message: Message):
    if message.from_user.id not in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data="a_bal")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd"), InlineKeyboardButton(text="🖼 Сменить фото", callback_data="a_photo")],
        [InlineKeyboardButton(text="👤 +Админ", callback_data="a_add"), InlineKeyboardButton(text="🧹 Очистить очередь", callback_data="a_clr")]
    ])
    await message.answer("🛠 Панель управления:", reply_markup=kb)

@router.callback_query(F.data == "a_bal")
async def adm_bal_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите Telegram ID пользователя:")
    await state.set_state(FSMSettings.edit_balance_id)

@router.message(FSMSettings.edit_balance_id)
async def adm_bal_2(message: Message, state: FSMContext):
    await state.update_data(target_id=message.text)
    await message.answer("Введите сумму (например 100 или -50):")
    await state.set_state(FSMSettings.edit_balance_sum)

@router.message(FSMSettings.edit_balance_sum)
async def adm_bal_3(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        amount = float(message.text)
        db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, data['target_id']), commit=True)
        await message.answer(f"✅ Баланс пользователя {data['target_id']} изменен на {amount} руб.")
        await bot.send_message(data['target_id'], f"🔔 Ваш баланс изменен на {amount} руб.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()

# --- СМЕНА ФОТО (ИСПРАВЛЕННАЯ) ---
@router.callback_query(F.data == "a_photo")
async def adm_photo_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришлите фото (картинкой):")
    await state.set_state(FSMSettings.photo)

@router.message(FSMSettings.photo, F.photo)
async def adm_photo_save(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    db_query('UPDATE settings SET value=? WHERE key="photo"', (file_id,), commit=True)
    await message.answer("✅ Фото успешно сохранено!")
    await state.clear()

# Остальные кнопки (Очередь, Вывод, Поддержка)
@router.message(F.text == "⏳ Очередь")
async def queue_show(message: Message):
    q = db_query('SELECT platform, tariff, phone FROM apps WHERE status="Ожидание"', fetchall=True)
    if not q: return await message.answer("Очередь пуста.")
    txt = "⏳ <b>Актуальная очередь:</b>\n"
    for i in q: txt += f"• {i[0]} ({i[1]}) | {i[2][:5]}***\n"
    await message.answer(txt)

@router.message(F.text == "💸 Вывод")
async def withdraw(message: Message):
    await message.answer("Для вывода средств напишите в поддержку: @твой_логин")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
