import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- НАСТРОЙКИ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
OWNER_ID = 8119723042
ADMIN_USER = "@ik_126" # Юзер для вывода
SUB_LINK = "https://t.me/+El8vWu80EDFjYjk6" # Ссылка на подписку

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('bot_final_v5.db')
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
def main_kb(uid):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    bal = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal_val = bal[0] if bal else 0
    kb = [
        [KeyboardButton(text=f"💰 Баланс: {bal_val} руб.")],
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in admins: kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ХЕНДЛЕРЫ ---
@router.message(CommandStart())
async def start(message: Message):
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = f"<b>Добро пожаловать!</b>\nДля работы подпишитесь на канал: {SUB_LINK}"
    try:
        if photo == "NONE": await message.answer(txt, reply_markup=main_kb(message.from_user.id))
        else: await message.answer_photo(photo=photo, caption=txt, reply_markup=main_kb(message.from_user.id))
    except: await message.answer(txt, reply_markup=main_kb(message.from_user.id))

# --- ВЫВОД СРЕДСТВ ---
@router.message(F.text == "💸 Вывод")
async def withdraw_money(message: Message):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
    balance = res[0] if res else 0
    
    if balance > 0:
        await message.answer(f"✅ Ваш баланс: <b>{balance} руб.</b>\nДля оформления выплаты напишите администратору: {ADMIN_USER}")
    else:
        await message.answer("❌ <b>Недостаточно средств.</b>\nВаш баланс 0 руб. Сдайте номер, чтобы заработать!")

# --- СДАЧА НОМЕРА ---
@router.message(F.text == "📱 Сдать номер")
async def app_1(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВК", callback_data="plat_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="plat_ВЦ")]
    ])
    await message.answer("Выберите платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@router.callback_query(F.data.startswith("plat_"))
async def app_2(call: CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[1]
    await state.update_data(platform=plat)
    if plat == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2/15м", callback_data="t_2/15м")],
            [InlineKeyboardButton(text="1.3/0м", callback_data="t_1.3/0м")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="3/20", callback_data="t_3/20")]])
    await call.message.edit_text(f"Выберите тариф для {plat}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@router.callback_query(F.data.startswith("t_"))
async def app_3(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[1])
    await call.message.edit_text("Введите номер телефона:")
    await state.set_state(FSMApp.phone)

@router.message(FSMApp.phone)
async def app_4(message: Message, state: FSMContext):
    data = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?, ?, ?, ?)', 
            (message.from_user.id, data['platform'], data['tariff'], message.text), commit=True)
    await message.answer("✅ Номер добавлен в очередь!", reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ (ОТДЕЛЬНЫЕ КНОПКИ) ---
@router.message(F.text == "⏳ Очередь")
async def queue_main(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очередь ВК", callback_data="q_view_ВК")],
        [InlineKeyboardButton(text="Очередь ВЦ", callback_data="q_view_ВЦ")]
    ])
    await message.answer("Выберите нужную очередь:", reply_markup=kb)

@router.callback_query(F.data.startswith("q_view_"))
async def queue_view(call: CallbackQuery):
    plat = call.data.split("_")[2]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    is_admin = call.from_user.id in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    if not rows:
        return await call.message.edit_text(f"Очередь {plat} пуста.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="q_back")]]))

    await call.message.edit_text(f"⏳ <b>Список очереди {plat}:</b>")
    for r in rows:
        txt = f"Заявка #{r[0]}\nТариф: {r[1]}\nНомер: {r[2]}"
        if is_admin:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Взять", callback_data=f"q_take_{r[0]}"),
                 InlineKeyboardButton(text="🗑 Удалить", callback_data=f"q_del_{r[0]}")]
            ])
            await call.message.answer(txt, reply_markup=kb)
        else:
            await call.message.answer(f"ID:{r[0]} | {r[1]} | {r[2][:5]}***")
    await call.answer()

@router.callback_query(F.data == "q_back")
async def q_back(call: CallbackQuery):
    await queue_main(call.message)

@router.callback_query(F.data.startswith("q_take_"))
async def q_take(call: CallbackQuery):
    app_id = call.data.split("_")[2]
    app = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (app_id,), fetchone=True)
    if app:
        await call.message.edit_text(f"🚀 <b>Данные получены:</b>\nЮзер: {app[0]}\nНомер: {app[1]}\nПлатформа: {app[2]}")
        db_query('DELETE FROM apps WHERE id=?', (app_id,), commit=True)
    await call.answer()

@router.callback_query(F.data.startswith("q_del_"))
async def q_del(call: CallbackQuery):
    db_query('DELETE FROM apps WHERE id=?', (call.data.split("_")[2],), commit=True)
    await call.message.delete()
    await call.answer("Удалено")

# --- АДМИНКА ---
@router.message(F.text == "⚙️ Админка")
async def admin_main(message: Message):
    if message.from_user.id not in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить Баланс", callback_data="a_bal")],
        [InlineKeyboardButton(text="🖼 Фото /start", callback_data="a_photo"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd")],
        [InlineKeyboardButton(text="🧹 Очистить ВК", callback_data="clr_ВК"), InlineKeyboardButton(text="🧹 Очистить ВЦ", callback_data="clr_ВЦ")],
        [InlineKeyboardButton(text="👤 +Админ", callback_data="a_add")]
    ])
    await message.answer("🛠 Панель администратора:", reply_markup=kb)

@router.callback_query(F.data.startswith("clr_"))
async def clr_q(call: CallbackQuery):
    plat = call.data.split("_")[1]
    db_query('DELETE FROM apps WHERE platform=?', (plat,), commit=True)
    await call.message.answer(f"🧹 Очередь {plat} очищена.")
    await call.answer()

@router.callback_query(F.data == "a_bal")
async def a_bal_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:"); await state.set_state(FSMAdmin.edit_bal_id)

@router.message(FSMAdmin.edit_bal_id)
async def a_bal_2(message: Message, state: FSMContext):
    await state.update_data(id=message.text); await message.answer("Сумма (например 100):"); await state.set_state(FSMAdmin.edit_bal_sum)

@router.message(FSMAdmin.edit_bal_sum)
async def a_bal_3(message: Message, state: FSMContext):
    data = await state.get_data(); amt = float(message.text)
    db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, data['id']), commit=True)
    await message.answer("✅ Баланс изменен!"); await state.clear()

@router.callback_query(F.data == "a_photo")
async def a_ph_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Отправьте новое фото:"); await state.set_state(FSMAdmin.photo)

@router.message(FSMAdmin.photo, F.photo)
async def a_ph_2(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Фото обновлено!"); await state.clear()

# --- ОТЧЕТ И ПОДДЕРЖКА ---
@router.message(F.text == "📊 Отчет")
async def report_1(message: Message, state: FSMContext):
    await message.answer("Введите ваш вопрос/претензию:"); await state.set_state(FSMReport.text)

@router.message(FSMReport.text)
async def report_2(message: Message, state: FSMContext):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    for a in adms: await bot.send_message(a, f"⚠️ <b>НОВЫЙ ОТЧЕТ:</b>\nОт: {message.from_user.id}\nТекст: {message.text}")
    await message.answer("✅ Отправлено."); await state.clear()

@router.message(F.text == "👨‍💻 Поддержка")
async def support_info(message: Message):
    await message.answer(f"Связь с администратором: {ADMIN_USER}")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
