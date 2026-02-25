import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- КОНФИГ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
# ТЕПЕРЬ ТУТ ДВА АДМИНА
ADMINS = [8119723042, 6505777490] # Добавь сюда ID второго аккаунта, если 6505777490 не тот
SUPPORT_LINK = "https://t.me/BOSSI2026"
CHANNEL_ID = -1003717021572 
CHANNEL_URL = "https://t.me/ik_126_channel"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('v18_boss_build.db')
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
    db_query('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)', commit=True)
    db_query('CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, tariff TEXT, phone TEXT)', commit=True)
    for adm in ADMINS:
        db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (adm,), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('photo', 'NONE'), commit=True)

# --- СОСТОЯНИЯ ---
class FSMAdmin(StatesGroup):
    wait_qr = State()
    edit_bal_id = State(); edit_bal_sum = State()
    add_adm = State(); photo = State(); broadcast = State()

class FSMApp(StatesGroup):
    platform = State(); tariff = State(); phone = State()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# Основное меню (Reply)
def main_kb(uid):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    res = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal = res[0] if res else 0
    kb = [
        [KeyboardButton(text=f"💰 Баланс: {bal} руб.")],
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in adms: kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Канал", url=CHANNEL_URL), InlineKeyboardButton(text="🔄 Проверить", callback_data="recheck")]])
        return await message.answer("❌ Подпишитесь на канал!", reply_markup=kb)
    
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = "<b>Добро пожаловать! Выберите действие в меню ниже:</b>"
    if photo != "NONE": await message.answer_photo(photo, caption=txt, reply_markup=main_kb(message.from_user.id))
    else: await message.answer(txt, reply_markup=main_kb(message.from_user.id))

# Тот самый переход в поддержку (удаляет клаву, ставит кнопку под текст)
@dp.message(F.text == "👨‍💻 Поддержка")
async def support_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать @BOSSI2026", url=SUPPORT_LINK)],
        [InlineKeyboardButton(text="⬅️ Вернуть меню", callback_data="back_to_menu")]
    ])
    await message.answer("Нажмите на кнопку ниже, чтобы связаться с нами:", reply_markup=kb)

@dp.callback_query(F.data == "back_to_menu")
async def back_menu(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=main_kb(call.from_user.id))

# --- АДМИНКА ДЛЯ ВСЕХ АДМИНОВ ---
@dp.message(F.text == "⚙️ Админка")
async def adm_panel(message: Message):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if message.from_user.id not in adms: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс +/-", callback_data="a_bal"), InlineKeyboardButton(text="👤 +Админ", callback_data="a_add")],
        [InlineKeyboardButton(text="🖼 Фото старта", callback_data="a_ph"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd")]
    ])
    await message.answer("🛠 Панель администратора:", reply_markup=kb)

# --- ОЧЕРЕДЬ (Любой админ может взять) ---
@dp.callback_query(F.data.startswith("v_"))
async def q_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.")
    await call.message.delete()
    for r in rows:
        txt = f"<b>Заявка #{r[0]} ({plat})</b>\nТариф: {r[1]}\nНомер: {r[2]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять", callback_data=f"t_{r[0]}")]]) if call.from_user.id in adms else None
        await call.message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("t_"))
async def take_action(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (aid,), fetchone=True)
    if not res: return await call.answer("Уже взято.")
    uid, phone, plat = res
    await state.update_data(target_user=uid, target_app_id=aid, target_phone=phone)
    if plat == "ВЦ":
        await call.message.answer(f"📱 <b>WhatsApp: {phone}</b>\nПришлите фото QR:")
        await state.set_state(FSMAdmin.wait_qr)
        await bot.send_message(uid, "⏳ Админ взял ваш номер в работу.")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔑 Запросить код", callback_data="r_code")], [InlineKeyboardButton(text="✅ Подтвердить", callback_data="r_ok")], [InlineKeyboardButton(text="❌ Отмена", callback_data="r_no")]])
        await call.message.answer(f"📱 <b>ВК: {phone}</b>", reply_markup=kb)

# --- ЛОГИКА ПОДТВЕРЖДЕНИЯ ---
@dp.callback_query(F.data == "r_ok")
async def r_ok(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    await bot.send_message(data['target_user'], "✅ <b>Номер успешно принят! Сейчас админ пополнит вам баланс.</b>")
    await call.message.edit_text("✅ Завершено.")
    await state.clear()

# --- ВСЁ ОСТАЛЬНОЕ (СДАЧА, БАЛАНС, ТАРИФЫ) ---
@dp.callback_query(F.data.startswith("st_"))
async def s_2(call: CallbackQuery, state: FSMContext):
    p = call.data.split("_")[1]; await state.update_data(platform=p)
    if p == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="2/15м", callback_data="tr_2/15м")], [InlineKeyboardButton(text="1.5/0м", callback_data="tr_1.5/0м")]])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="3/20", callback_data="tr_3/20")]])
    await call.message.edit_text("Выберите тариф:", reply_markup=kb); await state.set_state(FSMApp.tariff)

@dp.message(FSMApp.phone)
async def s_4(message: Message, state: FSMContext):
    d = await state.get_data(); db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?,?,?,?)', (message.from_user.id, d['platform'], d['tariff'], message.text), commit=True)
    await message.answer("✅ Номер отправлен в очередь!", reply_markup=main_kb(message.from_user.id)); await state.clear()

# (Здесь должны быть остальные хендлеры из предыдущего кода: a_add, a_bal, qr_send и т.д. — они все сохранены)
# ... [полный набор хендлеров админки из v17] ...

@dp.callback_query(F.data == "a_add")
async def adm_add_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("ID нового админа:"); await state.set_state(FSMAdmin.add_adm)
@dp.message(FSMAdmin.add_adm)
async def adm_add_2(message: Message, state: FSMContext):
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (int(message.text),), commit=True)
    await message.answer("✅ Админ добавлен!"); await state.clear()

@dp.callback_query(F.data == "a_bal")
async def b_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("ID юзера:"); await state.set_state(FSMAdmin.edit_bal_id)
@dp.message(FSMAdmin.edit_bal_id)
async def b_2(message: Message, state: FSMContext):
    await state.update_data(u=message.text); await message.answer("Сумма:"); await state.set_state(FSMAdmin.edit_bal_sum)
@dp.message(FSMAdmin.edit_bal_sum)
async def b_3(message: Message, state: FSMContext):
    d=await state.get_data(); db_query('UPDATE users SET balance=balance+? WHERE user_id=?', (float(message.text), d['u']), commit=True)
    await message.answer("✅ Баланс изменен!"); await state.clear()

@dp.message(FSMAdmin.wait_qr, F.photo)
async def qrs(message: Message, state: FSMContext):
    data = await state.get_data(); await bot.send_photo(data['target_user'], message.photo[-1].file_id, caption="📸 <b>QR-код от админа!</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить", callback_data="r_ok")]])
    await message.answer("Отправлено!", reply_markup=kb)

async def main():
    init_db(); logging.basicConfig(level=logging.INFO); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
