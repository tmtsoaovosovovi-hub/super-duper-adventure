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
CHANNEL_URL = "https://t.me/ik_126_channel"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('v16_perfect_build.db')
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
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,), commit=True)
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

# --- ГЛАВНЫЕ КОМАНДЫ ---

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Канал", url=CHANNEL_URL), InlineKeyboardButton(text="🔄 Проверить", callback_data="recheck")]])
        return await message.answer("❌ Подпишитесь на канал для доступа!", reply_markup=kb)
    
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = "<b>Добро пожаловать в сервис!</b>"
    if photo != "NONE": await message.answer_photo(photo, caption=txt, reply_markup=main_kb(message.from_user.id))
    else: await message.answer(txt, reply_markup=main_kb(message.from_user.id))

@dp.callback_query(F.data == "recheck")
async def recheck(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete(); await call.message.answer("✅ Доступ открыт!", reply_markup=main_kb(call.from_user.id))
    else: await call.answer("❌ Подписка не найдена", show_alert=True)

# --- ЛОГИКА АДМИНКИ (+АДМИН, БАЛАНС, ФОТО) ---

@dp.message(F.text == "⚙️ Админка")
async def adm_panel(message: Message):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if message.from_user.id not in adms: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс +/-", callback_data="a_bal"), InlineKeyboardButton(text="👤 +Админ", callback_data="a_add")],
        [InlineKeyboardButton(text="🖼 Фото старта", callback_data="a_ph"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd")]
    ])
    await message.answer("🛠 Панель администратора:", reply_markup=kb)

@dp.callback_query(F.data == "a_add")
async def adm_add_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Отправьте Telegram ID нового администратора:")
    await state.set_state(FSMAdmin.add_adm)
    await call.answer()

@dp.message(FSMAdmin.add_adm)
async def adm_add_step2(message: Message, state: FSMContext):
    if message.text.isdigit():
        new_id = int(message.text)
        db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (new_id,), commit=True)
        await message.answer(f"✅ Пользователь {new_id} добавлен в список админов!")
    else:
        await message.answer("❌ Ошибка! ID должен состоять только из цифр.")
    await state.clear()

@dp.callback_query(F.data == "a_ph")
async def adm_ph_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришлите новое фото для команды /start:"); await state.set_state(FSMAdmin.photo)

@dp.message(FSMAdmin.photo, F.photo)
async def adm_ph_step2(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Фото успешно обновлено!"); await state.clear()

@dp.callback_query(F.data == "a_bal")
async def adm_bal_step1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:"); await state.set_state(FSMAdmin.edit_bal_id)

@dp.message(FSMAdmin.edit_bal_id)
async def adm_bal_step2(message: Message, state: FSMContext):
    await state.update_data(uid=message.text); await message.answer("Сумма (например 100 или -50):"); await state.set_state(FSMAdmin.edit_bal_sum)

@dp.message(FSMAdmin.edit_bal_sum)
async def adm_bal_step3(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        amt = float(message.text)
        db_query('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, data['uid']), commit=True)
        await message.answer(f"✅ Баланс {data['uid']} изменен на {amt} руб."); await state.clear()
    except: await message.answer("❌ Ошибка! Введите число.")

# --- ОЧЕРЕДЬ И ВЗАИМОДЕЙСТВИЕ ---

@dp.message(F.text == "⏳ Очередь")
async def q_choice(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Очередь ВК", callback_data="v_ВК")], [InlineKeyboardButton(text="Очередь ВЦ", callback_data="v_ВЦ")]])
    await message.answer("Выберите очередь:", reply_markup=kb)

@dp.callback_query(F.data.startswith("v_"))
async def q_view(call: CallbackQuery):
    plat = call.data.split("_")[1]
    rows = db_query('SELECT id, tariff, phone FROM apps WHERE platform=?', (plat,), fetchall=True)
    is_adm = call.from_user.id in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.")
    await call.message.delete()
    for r in rows:
        txt = f"<b>Заявка #{r[0]} ({plat})</b>\nТариф: {r[1]}\nНомер: {r[2]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять", callback_data=f"t_{r[0]}")]]) if is_adm else None
        await call.message.answer(txt, reply_markup=kb)

@dp.callback_query(F.data.startswith("t_"))
async def take_action(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (aid,), fetchone=True)
    if not res: return await call.answer("Уже удалено.")
    uid, phone, plat = res
    await state.update_data(target_user=uid, target_app_id=aid, target_phone=phone)
    if plat == "ВЦ":
        await call.message.edit_text(f"📱 <b>WhatsApp: {phone}</b>\nПришлите ФОТО QR-кода:"); await state.set_state(FSMAdmin.wait_qr)
        await bot.send_message(uid, "⏳ Админ взял ваш номер (ВЦ). Ожидайте QR-код.")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔑 Запросить код", callback_data="r_code")], [InlineKeyboardButton(text="✅ Подтвердить", callback_data="r_ok")], [InlineKeyboardButton(text="❌ Отмена", callback_data="r_no")]])
        await call.message.edit_text(f"📱 <b>ВК: {phone}</b>", reply_markup=kb)

@dp.message(FSMAdmin.wait_qr, F.photo)
async def qr_send(message: Message, state: FSMContext):
    data = await state.get_data()
    await bot.send_photo(data['target_user'], message.photo[-1].file_id, caption="📸 <b>Ваш QR-код от админа!</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="r_ok")], [InlineKeyboardButton(text="❌ Отмена", callback_data="r_no")]])
    await message.answer("✅ Отправлено. Управление:", reply_markup=kb)

@dp.callback_query(F.data == "r_code")
async def r_code(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); await bot.send_message(data['target_user'], "⚠️ <b>Админ просит код!</b>"); await call.answer("Запрос отправлен")

@dp.callback_query(F.data == "r_ok")
async def r_ok(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    await bot.send_message(data['target_user'], "✅ Номер принят!"); await call.message.edit_text("✅ Завершено."); await state.clear()

@dp.callback_query(F.data == "r_no")
async def r_no(call: CallbackQuery, state: FSMContext):
    data = await state.get_data(); await bot.send_message(data['target_user'], "❌ Отказ."); await call.message.edit_text("❌ Отменено."); await state.clear()

# --- ВЫВОД, СДАЧА НОМЕРА, ПОДДЕРЖКА ---

@dp.message(F.text == "💸 Вывод")
async def draw(message: Message):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (message.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    if bal > 0: await message.answer(f"💰 Баланс: {bal} руб.\nПисать: {ADMIN_USER}")
    else: await message.answer("❌ Баланс 0.")

@dp.message(F.text == "📱 Сдать номер")
async def s_1(message: Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ВК", callback_data="st_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="st_ВЦ")]])
    await message.answer("Платформа:", reply_markup=kb); await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("st_"))
async def s_2(call: CallbackQuery, state: FSMContext):
    p = call.data.split("_")[1]; await state.update_data(platform=p)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="2/15м", callback_data="tr_2/15м")]] if p=="ВК" else [[InlineKeyboardButton(text="3/20", callback_data="tr_3/20")]])
    await call.message.edit_text("Тариф:", reply_markup=kb); await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("tr_"))
async def s_3(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[1]); await call.message.edit_text("Номер:"); await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def s_4(message: Message, state: FSMContext):
    d = await state.get_data(); db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?,?,?,?)', (message.from_user.id, d['platform'], d['tariff'], message.text), commit=True)
    await message.answer("✅ В очереди!", reply_markup=main_kb(message.from_user.id)); await state.clear()

@dp.message(F.text == "👨‍💻 Поддержка")
async def supp(message: Message): await message.answer(f"Поддержка: {ADMIN_USER}")

@dp.message(F.text == "📊 Отчет")
async def rep_1(message: Message, state: FSMContext):
    await message.answer("Текст отчета:"); await state.set_state(FSMAdmin.broadcast) # Используем как временное

@dp.callback_query(F.data == "a_brd")
async def broad_1(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Текст рассылки:"); await state.set_state(FSMAdmin.broadcast)
@dp.message(FSMAdmin.broadcast)
async def broad_2(message: Message, state: FSMContext):
    for u in db_query('SELECT user_id FROM users', fetchall=True):
        try: await bot.send_message(u[0], message.text)
        except: pass
    await message.answer("✅ Готово!"); await state.clear()

async def main():
    init_db(); logging.basicConfig(level=logging.INFO); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
