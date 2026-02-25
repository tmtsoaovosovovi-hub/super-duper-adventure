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
CHANNEL_ID = -1003717021572 
CHANNEL_URL = "https://t.me/ik_126_channel"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('v22_final_boss.db')
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
    wait_qr = State(); edit_bal_id = State(); edit_bal_sum = State()
    add_adm = State(); photo = State(); broadcast = State()

class FSMApp(StatesGroup):
    platform = State(); tariff = State(); phone = State()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- ГЛАВНОЕ ИНЛАЙН МЕНЮ ---
def get_main_inline(uid):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (uid,), fetchone=True)
    bal = res[0] if res else 0
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    
    kb = [
        [InlineKeyboardButton(text=f"💰 Баланс: {bal} руб.", callback_data="show_bal_info")],
        [InlineKeyboardButton(text="📱 Сдать номер", callback_data="app_start"), InlineKeyboardButton(text="📊 Отчет", callback_data="app_report")],
        [InlineKeyboardButton(text="⏳ Очередь", callback_data="q_start"), InlineKeyboardButton(text="💸 Вывод", callback_data="app_withdraw")],
        [InlineKeyboardButton(text="👨‍💻 Поддержка", url=SUPPORT_LINK)]
    ]
    if uid in adms:
        kb.append([InlineKeyboardButton(text="⚙️ Админка", callback_data="adm_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    
    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
            [InlineKeyboardButton(text="🔄 Проверить", callback_data="recheck")]
        ])
        return await message.answer("⚠️ Подпишитесь на канал для доступа!", reply_markup=kb)

    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    txt = "<b>Главное меню:</b>\nВыберите действие кнопками ниже."
    
    if photo != "NONE":
        await message.answer_photo(photo, caption=txt, reply_markup=get_main_inline(message.from_user.id))
    else:
        await message.answer(txt, reply_markup=get_main_inline(message.from_user.id))
    
    await message.answer("Меню загружено. Клавиатура скрыта.", reply_markup=ReplyKeyboardRemove())

@dp.callback_query(F.data == "recheck")
async def recheck(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Доступ открыт!", reply_markup=get_main_inline(call.from_user.id))
    else:
        await call.answer("❌ Подписка не найдена!", show_alert=True)

# --- ОБНОВЛЕННАЯ СДАЧА НОМЕРА (ТАРИФЫ) ---
@dp.callback_query(F.data == "app_start")
async def app_1(call: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ВК", callback_data="st_ВК"), InlineKeyboardButton(text="ВЦ", callback_data="st_ВЦ")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await call.message.edit_text("Выберите платформу:") if not call.message.photo else await call.message.edit_caption(caption="Выберите платформу:", reply_markup=kb)
    await state.set_state(FSMApp.platform)

@dp.callback_query(F.data.startswith("st_"))
async def app_2(call: CallbackQuery, state: FSMContext):
    p = call.data.split("_")[1]; await state.update_data(platform=p)
    if p == "ВК":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="2$/15мин", callback_data="tr_2/15м")],
            [InlineKeyboardButton(text="1.3$/0мин", callback_data="tr_1.3/0м")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="app_start")]
        ])
    else: # Для ВЦ (WhatsApp)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3$/20мин", callback_data="tr_3/20м")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="app_start")]
        ])
    
    txt = f"Выберите тариф для {p}:"
    if call.message.photo: await call.message.edit_caption(caption=txt, reply_markup=kb)
    else: await call.message.edit_text(txt, reply_markup=kb)
    await state.set_state(FSMApp.tariff)

@dp.callback_query(F.data.startswith("tr_"))
async def app_3(call: CallbackQuery, state: FSMContext):
    await state.update_data(tariff=call.data.split("_")[1])
    await call.message.answer("<b>Введите номер телефона:</b>")
    await state.set_state(FSMApp.phone)

@dp.message(FSMApp.phone)
async def app_4(message: Message, state: FSMContext):
    d = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, tariff, phone) VALUES (?,?,?,?)', (message.from_user.id, d['platform'], d['tariff'], message.text), commit=True)
    await message.answer("✅ Номер добавлен в очередь!", reply_markup=get_main_inline(message.from_user.id))
    await state.clear()

# --- ОСТАЛЬНАЯ ЛОГИКА (ОЧЕРЕДЬ, АДМИНКА) ---

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
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    if not rows: return await call.message.edit_text(f"Очередь {plat} пуста.", reply_markup=get_main_inline(call.from_user.id))
    
    await call.message.delete()
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Взять номер", callback_data=f"take_{r[0]}")]]) if call.from_user.id in adms else None
        await call.message.answer(f"<b>Заявка #{r[0]} ({plat})</b>\nТариф: {r[1]}\nНомер: {r[2]}", reply_markup=kb)

@dp.callback_query(F.data.startswith("take_"))
async def take_logic(call: CallbackQuery, state: FSMContext):
    aid = call.data.split("_")[1]
    res = db_query('SELECT user_id, phone, platform FROM apps WHERE id=?', (aid,), fetchone=True)
    if not res: return await call.answer("Заявка уже взята.")
    uid, phone, plat = res
    await state.update_data(target_user=uid, target_app_id=aid)
    
    if plat == "ВЦ":
        await call.message.answer(f"📱 <b>WhatsApp: {phone}</b>\nПришлите фото QR-кода:"); await state.set_state(FSMAdmin.wait_qr)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Запросить код", callback_data="r_code")],
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="r_ok")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="r_no")]
        ])
        await call.message.answer(f"📱 <b>ВК: {phone}</b>", reply_markup=kb)

@dp.callback_query(F.data == "r_ok")
async def r_ok(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    db_query('DELETE FROM apps WHERE id=?', (data['target_app_id'],), commit=True)
    await bot.send_message(data['target_user'], "✅ <b>Номер успешно принят! Сейчас админ пополнит вам баланс.</b>")
    await call.message.answer("✅ Заявка завершена!", reply_markup=get_main_inline(call.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "back_main")
async def b_m(call: CallbackQuery):
    if call.message.photo: await call.message.edit_caption(caption="Главное меню:", reply_markup=get_main_inline(call.from_user.id))
    else: await call.message.edit_text("Главное меню:", reply_markup=get_main_inline(call.from_user.id))

@dp.callback_query(F.data == "adm_panel")
async def adm_p(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс юзера", callback_data="a_bal"), InlineKeyboardButton(text="👤 +Админ", callback_data="a_add")],
        [InlineKeyboardButton(text="🖼 Сменить фото", callback_data="a_ph"), InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    await call.message.edit_text("Панель администратора:", reply_markup=kb)

@dp.callback_query(F.data == "show_bal_info")
async def show_bal(call: CallbackQuery):
    res = db_query('SELECT balance FROM users WHERE user_id=?', (call.from_user.id,), fetchone=True)
    bal = res[0] if res else 0
    await call.answer(f"Твой баланс: {bal} руб.", show_alert=True)

@dp.callback_query(F.data == "app_withdraw")
async def wd(call: CallbackQuery):
    await call.message.edit_text(f"Для вывода средств пишите в поддержку:\n{SUPPORT_LINK}", reply_markup=get_main_inline(call.from_user.id))

# --- ЗАПУСК ---
async def main():
    init_db(); logging.basicConfig(level=logging.INFO); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
