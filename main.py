import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- КОНФИГ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
OWNER_ID = 8119723042
ADMIN_USER = "@ik_126"
SUB_LINK = "https://t.me/+El8vWu80EDFjYjk6"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('bot_v11_final.db')
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        res = None
        if fetchone: res = cursor.fetchone()
        if fetchall: res = cursor.fetchall()
        if commit: conn.commit()
        return res
    finally:
        conn.close()

def init_db():
    queries = [
        'CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)',
        'CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)',
        'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)',
        'CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, tariff TEXT, phone TEXT)'
    ]
    for q in queries: db_query(q, commit=True)
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('photo', 'NONE'), commit=True)

# --- СОСТОЯНИЯ ---
class FSMAdmin(StatesGroup):
    photo = State()
    add_adm = State()
    broadcast = State()
    edit_bal_id = State()
    edit_bal_sum = State()

class FSMApp(StatesGroup):
    platform = State()
    tariff = State()
    phone = State()

class FSMReport(StatesGroup):
    text = State()

# --- КЛАВИАТУРЫ ---
def get_main_kb(uid):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    bal = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal_val = bal[0] if bal else 0
    
    kb = [
        [KeyboardButton(text=f"💰 Баланс: {bal_val} руб.")],
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in admins:
        kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ОБЩИЕ ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = f"Привет! Подпишись на наш канал: {SUB_LINK}\nИспользуй кнопки ниже для работы."
    
    if photo != "NONE":
        try:
            await message.answer_photo(photo=photo, caption=txt, reply_markup=get_main_kb(message.from_user.id))
            return
        except: pass
    await message.answer(txt, reply_markup=get_main_kb(message.from_user.id))

@dp.message(F.text == "👨‍💻 Поддержка")
async def support(message: Message):
    await message.answer(f"Связь с администратором: {ADMIN_USER}")

@dp.message(F.text == "💸 Вывод")
async def withdraw(message: Message):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
    balance = res[0] if res else 0
    if balance > 0:
        await message.answer(f"✅ Ваш баланс: {balance} руб.\nДля вывода напишите: {ADMIN_USER}")
    else:
        await message.answer("❌ Недостаточно средств. Ваш баланс 0 руб.")

# --- СДАЧА НОМЕРА ---

@dp.message(F.text == "📱 Сдать номер")
async def start_app(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="ВК", callback_data="set_plat_ВК"),
        InlineKeyboardButton(text="ВЦ", callback_data="set_plat_ВЦ")
    ]])
    await message.answer("Выберите платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("set_plat_"))
async def set_platform(call: CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[2]
    await state.update_data(platform=plat)
    if plat == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2/15м", callback_data="set_tar_2/15м")],
            [InlineKeyboardButton(text="1.3/0м", callback_data="set_tar_1.3/0м")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="3/20", callback_data="set_tar_3/20")]])
    await call.message.edit_text(f"Выберите тариф для {plat}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("set_tar_"))
async def set_tariff(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[2])
    await call.message.edit_text("Введите номер телефона:")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def get_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?, ?, ?, ?)', 
            (message.from_user.id, data['platform'], data['tariff'], message.text), commit=True)
    await message.answer("✅ Номер добавлен в очередь!", reply_markup=get_main_kb(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ ---

@dp.message(F.text == "⏳ Очередь")
async def queue_choice(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очередь ВК", callback_data="view_q_ВК")],
        [InlineKeyboardButton(text="Очередь ВЦ", callback_data="view_q_ВЦ")]
    ])
    await message.answer("Какую очередь открыть?", reply_markup=kb)

@dp.callback_query(F.data.startswith("view_q_"))
async def view_queue(call: CallbackQuery):
    plat = call.data.split("_")[2]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    if not rows:
        await call.message.edit_text(f"Очередь {plat} пуста.")
        return

    await call.message.delete()
    for r in rows:
        txt = f"#{r[0]} | {plat} | {r[1]}\nНомер: {r[2]}"
        if call.from_user.id in admins:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Взять", callback_data=f"take_{r[0]}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{r[0]}")
            ]])
            await call.message.answer(txt, reply_markup=kb)
        else:
            await call.message.answer(f"ID:{r[0]} | {r[1]} | {r[2][:5]}***")

@dp.callback_query(F.data.startswith("take_"))
async def take_app(call: CallbackQuery):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone FROM apps WHERE id=?', (aid,), fetchone=True)
    if res:
        await call.message.edit_text(f"🚀 Взято в работу!\nЮзер ID: <code>{res[0]}</code>\nНомер: <code>{res[1]}</code>")
        db_query('DELETE FROM apps WHERE id=?', (aid,), commit=True)
    await call.answer()

@dp.callback_query(F.data.startswith("del_"))
async def del_app(call: CallbackQuery):
    db_query('DELETE FROM apps WHERE id=?', (call.data.split("_")[1],), commit=True)
    await call.message.delete()
    await call.answer("Удалено")

# --- АДМИН ПАНЕЛЬ ---

@dp.message(F.text == "⚙️ Админка")
async def admin_panel(message: Message):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if message.from_user.id not in admins: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс +/-", callback_data="adm_bal")],
        [InlineKeyboardButton(text="🖼 Фото /start", callback_data="adm_photo"), InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_brd")],
        [InlineKeyboardButton(text="🧹 Очистить ВК", callback_data="clear_ВК"), InlineKeyboardButton(text="🧹 Очистить ВЦ", callback_data="clear_ВЦ")],
        [InlineKeyboardButton(text="👤 +Админ", callback_data="adm_add")]
    ])
    await message.answer("🛠 Панель администратора:", reply_markup=kb)

# Хендлер +Админ
@dp.callback_query(F.data == "adm_add")
async def add_admin_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Отправьте Telegram ID пользователя, чтобы сделать его админом:")
    await state.set_state(FSMAdmin.add_adm)
    await call.answer()

@dp.message(FSMAdmin.add_adm)
async def add_admin_step2(message: Message, state: FSMContext):
    try:
        new_id = int(message.text)
        db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (new_id,), commit=True)
        await message.answer(f"✅ Пользователь {new_id} теперь админ!")
    except:
        await message.answer("❌ Ошибка. Введите числовой ID.")
    await state.clear()

# Хендлер Рассылка
@dp.callback_query(F.data == "adm_brd")
async def broadcast_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите текст рассылки для всех пользователей:")
    await state.set_state(FSMAdmin.broadcast)
    await call.answer()

@dp.message(FSMAdmin.broadcast)
async def broadcast_step2(message: Message, state: FSMContext):
    users = db_query('SELECT user_id FROM users', fetchall=True)
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка завершена. Получили {count} чел.")
    await state.clear()

@dp.callback_query(F.data.startswith("clear_"))
async def clear_queue_action(call: CallbackQuery):
    plat = call.data.split("_")[1]
    db_query('DELETE FROM apps WHERE platform=?', (plat,), commit=True)
    await call.message.answer(f"✅ Очередь {plat} полностью очищена!")
    await call.answer()

@dp.callback_query(F.data == "adm_bal")
async def edit_bal_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:"); await state.set_state(FSMAdmin.edit_bal_id)

@dp.message(FSMAdmin.edit_bal_id)
async def edit_bal_step2(message: Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Введите сумму (например, 100 или -50):"); await state.set_state(FSMAdmin.edit_bal_sum)

@dp.message(FSMAdmin.edit_bal_sum)
async def edit_bal_step3(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        amount = float(message.text)
        db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, data['uid']), commit=True)
        await message.answer(f"✅ Баланс пользователя {data['uid']} изменен на {amount} руб.")
    except: await message.answer("❌ Ошибка в сумме.")
    await state.clear()

@dp.callback_query(F.data == "adm_photo")
async def change_photo_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришлите фото (как картинку):"); await state.set_state(FSMAdmin.photo)

@dp.message(FSMAdmin.photo, F.photo)
async def change_photo_step2(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Фото старта обновлено!")
    await state.clear()

# --- ОТЧЕТ ---
@dp.message(F.text == "📊 Отчет")
async def report_step1(message: Message, state: FSMContext):
    await message.answer("Опишите ваш вопрос или проблему (одним сообщением):")
    await state.set_state(FSMReport.text)

@dp.message(FSMReport.text)
async def report_step2(message: Message, state: FSMContext):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    for a in adms:
        try: await bot.send_message(a, f"📊 <b>ОТЧЕТ от {message.from_user.id}:</b>\n{message.text}")
        except: pass
    await message.answer("✅ Отчет отправлен админам.", reply_markup=get_main_kb(message.from_user.id))
    await state.clear()

# --- ЗАПУСК ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
