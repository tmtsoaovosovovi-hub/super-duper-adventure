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
CHANNEL_ID = -1003717021572 
CHANNEL_URL = "https://t.me/ik_126_channel" # Укажи рабочую ссылку на канал

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ (авто-создание при запуске) ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('main_base_v13.db')
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
    db_query('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, tariff TEXT, phone TEXT)', commit=True)
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('photo', 'NONE'), commit=True)

# --- СОСТОЯНИЯ FSM ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def is_subscribed(user_id):
    if user_id in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]:
        return True
    try:
        chat_member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def main_kb(uid):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    res = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal = res[0] if res else 0
    kb = [
        [KeyboardButton(text=f"💰 Баланс: {bal} руб.")],
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in admins: kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="recheck")]
        ])
        return await message.answer("⚠️ <b>Доступ закрыт!</b>\nПодпишись на канал, чтобы пользоваться ботом.", reply_markup=kb)

    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    cap = "<b>Добро пожаловать!</b>\nСдавай номера и получай выплаты."
    if photo != "NONE":
        await message.answer_photo(photo=photo, caption=cap, reply_markup=main_kb(message.from_user.id))
    else:
        await message.answer(cap, reply_markup=main_kb(message.from_user.id))

@dp.callback_query(F.data == "recheck")
async def recheck(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Подписка подтверждена!", reply_markup=main_kb(call.from_user.id))
    else:
        await call.answer("❌ Ты всё еще не подписан!", show_alert=True)

# --- СДАЧА НОМЕРА ---
@dp.message(F.text == "📱 Сдать номер")
async def app_p1(message: Message, state: FSMContext):
    if not await is_subscribed(message.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="ВК", callback_data="p_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="p_ВЦ")
    ]])
    await message.answer("Выбери платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("p_"))
async def app_p2(call: CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[1]
    await state.update_data(platform=plat)
    if plat == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2/15м", callback_data="t_2/15м")],
            [InlineKeyboardButton(text="1.3/0м", callback_data="t_1.3/0м")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="3/20", callback_data="t_3/20")]])
    await call.message.edit_text(f"Выбери тариф для {plat}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("t_"))
async def app_p3(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[1])
    await call.message.edit_text("Введи номер телефона:")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def app_p4(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?, ?, ?, ?)', 
            (message.from_user.id, data['platform'], data['tariff'], message.text), commit=True)
    await message.answer("✅ Номер добавлен в очередь!", reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ ---
@dp.message(F.text == "⏳ Очередь")
async def queue_choice(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очередь ВК", callback_data="q_ВК")],
        [InlineKeyboardButton(text="Очередь ВЦ", callback_data="q_ВЦ")]
    ])
    await message.answer("Какую очередь показать?", reply_markup=kb)

@dp.callback_query(F.data.startswith("q_"))
async def queue_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    is_adm = call.from_user.id in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.")
    await call.message.delete()
    for r in rows:
        txt = f"<b>Заявка #{r[0]} ({plat})</b>\nТариф: {r[1]}\nНомер: {r[2]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Взять", callback_data=f"take_{r[0]}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{r[0]}")
        ]]) if is_adm else None
        await call.message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("take_"))
async def take_op(call: CallbackQuery):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (aid,), fetchone=True)
    if res:
        await call.message.edit_text(f"🚀 <b>Данные:</b>\nЮзер: <code>{res[0]}</code>\nНомер: <code>{res[1]}</code>\nПлатформа: {res[2]}")
        db_query('DELETE FROM apps WHERE id=?', (aid,), commit=True)

@dp.callback_query(F.data.startswith("del_"))
async def del_op(call: CallbackQuery):
    db_query('DELETE FROM apps WHERE id=?', (call.data.split("_")[1],), commit=True)
    await call.message.delete()

# --- ВЫВОД И ПОДДЕРЖКА ---
@dp.message(F.text == "💸 Вывод")
async def withdraw(message: Message):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    if bal > 0:
        await message.answer(f"💰 Баланс: {bal} руб.\nДля вывода пиши: {ADMIN_USER}")
    else:
        await message.answer("❌ Недостаточно средств для вывода.")

@dp.message(F.text == "👨‍💻 Поддержка")
async def support(message: Message):
    await message.answer(f"Связь с администратором: {ADMIN_USER}")

# --- АДМИНКА ---
@dp.message(F.text == "⚙️ Админка")
async def adm_panel(message: Message):
    if message.from_user.id not in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс +/-", callback_data="a_bal"), InlineKeyboardButton(text="👤 +Админ", callback_data="a_add")],
        [InlineKeyboardButton(text="🖼 Сменить Фото", callback_data="a_ph"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd")],
        [InlineKeyboardButton(text="🧹 Чистка ВК", callback_data="c_ВК"), InlineKeyboardButton(text="🧹 Чистка ВЦ", callback_data="c_ВЦ")]
    ])
    await message.answer("🛠 Панель управления:", reply_markup=kb)

@dp.callback_query(F.data.startswith("c_"))
async def clear_q(call: CallbackQuery):
    db_query('DELETE FROM apps WHERE platform=?', (call.data.split("_")[1],), commit=True)
    await call.message.answer("✅ Очищено!"); await call.answer()

@dp.callback_query(F.data == "a_add")
async def a_add_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID нового админа:"); await state.set_state(FSMAdmin.add_adm)

@dp.message(FSMAdmin.add_adm)
async def a_add_2(message: Message, state: FSMContext):
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (int(message.text),), commit=True)
    await message.answer("✅ Админ добавлен!"); await state.clear()

@dp.callback_query(F.data == "a_bal")
async def a_bal_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:"); await state.set_state(FSMAdmin.edit_bal_id)

@dp.message(FSMAdmin.edit_bal_id)
async def a_bal_2(message: Message, state: FSMContext):
    await state.update_data(uid=message.text); await message.answer("Сумма (число):"); await state.set_state(FSMAdmin.edit_bal_sum)

@dp.message(FSMAdmin.edit_bal_sum)
async def a_bal_3(message: Message, state: FSMContext):
    data = await state.get_data(); amt = float(message.text)
    db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, data['uid']), commit=True)
    await message.answer(f"✅ Баланс {data['uid']} изменен!"); await state.clear()

@dp.callback_query(F.data == "a_brd")
async def brd_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите текст рассылки:"); await state.set_state(FSMAdmin.broadcast)

@dp.message(FSMAdmin.broadcast)
async def brd_2(message: Message, state: FSMContext):
    for u in db_query('SELECT user_id FROM users', fetchall=True):
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("✅ Рассылка готова!"); await state.clear()

@dp.callback_query(F.data == "a_ph")
async def ph_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришли новое фото:"); await state.set_state(FSMAdmin.photo)

@dp.message(FSMAdmin.photo, F.photo)
async def ph_2(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Фото обновлено!"); await state.clear()

# --- ОТЧЕТ ---
@dp.message(F.text == "📊 Отчет")
async def rep_1(message: Message, state: FSMContext):
    await message.answer("Опишите проблему:"); await state.set_state(FSMReport.text)

@dp.message(FSMReport.text)
async def rep_2(message: Message, state: FSMContext):
    for a in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]:
        try: await bot.send_message(a, f"📊 ОТЧЕТ от {message.from_user.id}:\n{message.text}")
        except: pass
    await message.answer("✅ Отправлено."); await state.clear()

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
