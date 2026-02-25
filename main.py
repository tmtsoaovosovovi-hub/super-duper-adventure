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
# Список ID админов (добавь свои ID сюда)
ADMINS = [8119723042, 8377754197, 8330987864] 
SUPPORT_LINK = "https://t.me/BOSSI2026"
CHANNEL_ID = -1003717021572 
CHANNEL_URL = "https://t.me/ik_126_channel"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('bot_final_pro_v19.db')
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

# --- СОСТОЯНИЯ (FSM) ---
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

# --- КЛАВИАТУРЫ ---
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

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="recheck")]
        ])
        return await message.answer("⚠️ <b>Доступ ограничен!</b>\nДля работы с ботом подпишитесь на наш канал.", reply_markup=kb)

    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = "<b>Добро пожаловать!</b>\nИспользуйте меню для работы с сервисом."
    if photo != "NONE":
        await message.answer_photo(photo, caption=txt, reply_markup=main_kb(message.from_user.id))
    else:
        await message.answer(txt, reply_markup=main_kb(message.from_user.id))

@dp.callback_query(F.data == "recheck")
async def recheck_sub(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Подписка подтверждена!", reply_markup=main_kb(call.from_user.id))
    else:
        await call.answer("❌ Вы всё еще не подписаны!", show_alert=True)

# --- ЛОГИКА ПОДДЕРЖКИ (КНОПКА СВЕРХУ) ---
@dp.message(F.text == "👨‍💻 Поддержка")
async def support_info(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Написать в поддержку", url=SUPPORT_LINK)],
        [InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_to_menu")]
    ])
    await message.answer("<b>Связь с администрацией:</b>\nНажмите на кнопку ниже для перехода.", reply_markup=kb)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("Главное меню:", reply_markup=main_kb(call.from_user.id))

# --- СДАЧА НОМЕРА ---
@dp.message(F.text == "📱 Сдать номер")
async def app_1(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="ВК", callback_data="st_ВК"),
        InlineKeyboardButton(text="ВЦ", callback_data="st_ВЦ")
    ]])
    await message.answer("Выберите платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("st_"))
async def app_2(call: CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[1]
    await state.update_data(platform=plat)
    if plat == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2/15м", callback_data="tr_2/15м")],
            [InlineKeyboardButton(text="1.5/0м", callback_data="tr_1.5/0м")]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="3/20", callback_data="tr_3/20")]])
    await call.message.edit_text(f"Тариф для {plat}:", reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("tr_"))
async def app_3(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[1])
    await call.message.edit_text("Введите номер телефона:")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def app_4(message: Message, state: FSMContext):
    d = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?,?,?,?)', 
             (message.from_user.id, d['platform'], d['tariff'], message.text), commit=True)
    await message.answer("✅ Номер добавлен в очередь!", reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- ОЧЕРЕДЬ (РАБОТА АДМИНА) ---
@dp.message(F.text == "⏳ Очередь")
async def queue_choice(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очередь ВК", callback_data="v_ВК")],
        [InlineKeyboardButton(text="Очередь ВЦ", callback_data="v_ВЦ")]
    ])
    await message.answer("Какую очередь открыть?", reply_markup=kb)

@dp.callback_query(F.data.startswith("v_"))
async def queue_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.")
    
    await call.message.delete()
    for r in rows:
        txt = f"<b>Заявка #{r[0]} ({plat})</b>\nТариф: {r[1]}\nНомер: {r[2]}"
        # Кнопка доступна любому админу
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять", callback_data=f"take_{r[0]}")]]) if call.from_user.id in adms else None
        await call.message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("take_"))
async def take_logic(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (aid,), fetchone=True)
    if not res: return await call.answer("Заявка уже взята другим админом.")
    
    uid, phone, plat = res
    await state.update_data(target_user=uid, target_app_id=aid, target_phone=phone)
    
    if plat == "ВЦ":
        await call.message.answer(f"📱 <b>WhatsApp: {phone}</b>\nПришлите фото QR-кода админа:")
        await state.set_state(FSMAdmin.wait_qr)
        await bot.send_message(uid, "⏳ Админ начал работу с вашим номером (ВЦ). Ожидайте QR.")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Запросить код", callback_data="req_code")],
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_app")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_app")]
        ])
        await call.message.answer(f"📱 <b>ВК: {phone}</b>\nУправление:", reply_markup=kb)

@dp.message(FSMAdmin.wait_qr, F.photo)
async def qr_forward(message: Message, state: FSMContext):
    data = await state.get_data()
    await bot.send_photo(data['target_user'], message.photo[-1].file_id, caption="📸 <b>QR-код для входа от админа!</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_app")]])
    await message.answer("✅ QR отправлен юзеру. Нажмите подтвердить после входа:", reply_markup=kb)

@dp.callback_query(F.data == "req_code")
async def req_code(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await bot.send_message(data['target_user'], "⚠️ <b>Админ просит код!</b> Посмотрите SMS или уведомление.")
    await call.answer("Запрос отправлен!")

@dp.callback_query(F.data == "confirm_app")
async def confirm_app(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    await bot.send_message(data['target_user'], "✅ <b>Номер успешно принят! Сейчас админ пополнит вам баланс.</b>")
    await call.message.answer("✅ Работа завершена. Не забудь начислить баланс.")
    await state.clear()

@dp.callback_query(F.data == "cancel_app")
async def cancel_app(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await bot.send_message(data['target_user'], "❌ <b>Заявка отклонена.</b> Номер не подошел.")
    await call.message.answer("❌ Отменено.")
    await state.clear()

# --- АДМИНКА (БАЛАНС, ФОТО, +АДМИН) ---
@dp.message(F.text == "⚙️ Админка")
async def admin_menu(message: Message):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if message.from_user.id not in adms: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс +/-", callback_data="adm_bal"), InlineKeyboardButton(text="👤 +Админ", callback_data="adm_add")],
        [InlineKeyboardButton(text="🖼 Фото старта", callback_data="adm_photo"), InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_brd")]
    ])
    await message.answer("🛠 Панель управления:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add")
async def adm_add_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите Telegram ID нового админа:"); await state.set_state(FSMAdmin.add_adm)

@dp.message(FSMAdmin.add_adm)
async def adm_add_2(message: Message, state: FSMContext):
    if message.text.isdigit():
        db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (int(message.text),), commit=True)
        await message.answer("✅ Админ добавлен!")
    await state.clear()

@dp.callback_query(F.data == "adm_bal")
async def adm_bal_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:"); await state.set_state(FSMAdmin.edit_bal_id)

@dp.message(FSMAdmin.edit_bal_id)
async def adm_bal_2(message: Message, state: FSMContext):
    await state.update_data(uid=message.text); await message.answer("Сумма (например 100 или -50):"); await state.set_state(FSMAdmin.edit_bal_sum)

@dp.message(FSMAdmin.edit_bal_sum)
async def adm_bal_3(message: Message, state: FSMContext):
    d = await state.get_data()
    db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (float(message.text), d['uid']), commit=True)
    await message.answer("✅ Баланс обновлен!"); await state.clear()

@dp.callback_query(F.data == "adm_photo")
async def adm_photo_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришлите новое фото для /start:"); await state.set_state(FSMAdmin.photo)

@dp.message(FSMAdmin.photo, F.photo)
async def adm_photo_2(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Фото старта обновлено!"); await state.clear()

@dp.callback_query(F.data == "adm_brd")
async def adm_brd_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите текст рассылки:"); await state.set_state(FSMAdmin.broadcast)

@dp.message(FSMAdmin.broadcast)
async def adm_brd_2(message: Message, state: FSMContext):
    users = db_query('SELECT user_id FROM users', fetchall=True)
    for u in users:
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("✅ Рассылка завершена!"); await state.clear()

# --- ВЫВОД И ОТЧЕТЫ ---
@dp.message(F.text == "💸 Вывод")
async def withdraw_cmd(message: Message):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    if bal > 0:
        await message.answer(f"💰 Ваш баланс: {bal} руб.\nДля вывода средств пишите в поддержку.")
    else:
        await message.answer("❌ На балансе 0 руб.")

@dp.message(F.text == "📊 Отчет")
async def report_cmd(message: Message, state: FSMContext):
    await message.answer("Опишите проблему или отправьте скриншот:"); await state.set_state(FSMAdmin.broadcast) # Используем тот же буфер

# --- ЗАПУСК ---
async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
