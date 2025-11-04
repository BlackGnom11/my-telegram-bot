import asyncio
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import re

# Состояния для FSM
class PillForm(StatesGroup):
    name = State()
    time = State()


TOKEN = "8117367020:AAHuDsq2dTtk29-p_-BRekW1Eiw3DS1Sse8"

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

DATA_FILE = "data.json"

# === Вспомогательные функции ===

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_data()
pill_status = {}  # для отслеживания, принята ли таблетка

# === Меню ===

def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="➕ Добавить таблетку")
    kb.button(text="📋 Мои таблетки")
    kb.button(text="📞 Звонок Александру")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# === Логика напоминаний ===

async def send_reminder(chat_id: int, pill_name: str):
    """Отправить первое напоминание"""
    pill_id = f"{chat_id}_{pill_name}"
    pill_status[pill_id] = False

    kb = InlineKeyboardBuilder()
    kb.button(text="💧 Выпил", callback_data=f"done_{pill_id}")
    await bot.send_message(chat_id, f"💊 Напоминание: пора принять **{pill_name}**!", reply_markup=kb.as_markup())

    # Запускаем повтор через 15 минут, если не отмечено
    scheduler.add_job(send_repeat_reminder, "date", run_date=datetime.now() + timedelta(minutes=15), args=[chat_id, pill_name])

async def send_repeat_reminder(chat_id: int, pill_name: str):
    """Если не выпил — повторяем"""
    pill_id = f"{chat_id}_{pill_name}"
    if not pill_status.get(pill_id, False):
        kb = InlineKeyboardBuilder()
        kb.button(text="💧 Выпил", callback_data=f"done_{pill_id}")
        await bot.send_message(chat_id, f"⚠️ Ты ещё не выпил **{pill_name}**! Пора 💊", reply_markup=kb.as_markup())
        # Запускаем следующий повтор через 15 мин
        scheduler.add_job(send_repeat_reminder, "date", run_date=datetime.now() + timedelta(minutes=15), args=[chat_id, pill_name])

@dp.callback_query(F.data.startswith("done_"))
async def pill_done(callback: types.CallbackQuery):
    pill_id = callback.data.replace("done_", "")
    pill_status[pill_id] = True
    await callback.message.answer("✅ Отлично! Таблетка принята 💪")
    await callback.answer()

# === Обработчики ===

@dp.message(F.text == "/start")
async def start(message: types.Message):
    chat_id = str(message.chat.id)
    user_data.setdefault(chat_id, {"pills": []})
    save_data(user_data)
    await message.answer(
        "👋 Привет! Я твой заботливый бот 💊\n\n"
        "Буду напоминать тебе вовремя пить таблетки 😄\n"
        "Выбери действие 👇",
        reply_markup=main_menu()
    )

class PillForm(StatesGroup):
    name = State()
    time = State()

# Команда "Добавить таблетку"
@dp.message(F.text == "➕ Добавить таблетку")
async def add_pill(message: types.Message, state: FSMContext):
    await message.answer("📝 Напиши название таблетки:")
    await state.set_state(PillForm.name)

# Получаем название таблетки
@dp.message(PillForm.name)
async def get_pill_name(message: types.Message, state: FSMContext):
    pill_name = message.text.strip()
    await state.update_data(new_pill={"name": pill_name})
    await message.answer("⏰ Введи время приёма в формате HH:MM (например, 09:30):")
    await state.set_state(PillForm.time)

# Получаем время таблетки
@dp.message(PillForm.time)
async def get_pill_time(message: types.Message, state: FSMContext):
    time_text = message.text.strip()
    if not re.match(r"^\d{2}:\d{2}$", time_text):
        await message.answer("❌ Неверный формат. Попробуй снова, например `08:45`")
        return

    try:
        h, m = map(int, time_text.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError

        data = await state.get_data()
        pill_info = data["new_pill"]
        pill_info["time"] = time_text

        chat_id = str(message.chat.id)
        user_data[chat_id]["pills"].append(pill_info)
        save_data(user_data)

        # Добавляем напоминание
        scheduler.add_job(send_reminder, "cron", hour=h, minute=m, args=[int(chat_id), pill_info["name"]])

        await message.answer(f"✅ Добавил таблетку **{pill_info['name']}** на {time_text} 🕓", reply_markup=main_menu())
        await state.clear()  # очищаем состояние
    except ValueError:
        await message.answer("❌ Неверный формат. Попробуй снова, например `08:45`")


@dp.message(F.text == "📋 Мои таблетки")
async def show_pills(message: types.Message):
    chat_id = str(message.chat.id)
    pills = user_data.get(chat_id, {}).get("pills", [])
    if not pills:
        await message.answer("😅 У тебя пока нет добавленных таблеток.", reply_markup=main_menu())
    else:
        text = "💊 Твои таблетки:\n\n"
        for p in pills:
            text += f"• {p['name']} — {p['time']}\n"
        await message.answer(text, reply_markup=main_menu())


@dp.message(F.text == "📞 Звонок Александру")
async def call_alex(message: types.Message):
    # Inline-кнопка для перехода к пользователю с заранее заполненным сообщением
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Давай, ты сможешь",
            url="https://t.me/voznikla?text=Привет,Сань))"
            )
        ]
    ])

    await message.answer(
        "Спишь?)",
        reply_markup=keyboard
    )

ADMIN_ID = 1553754712 # 🔹 сюда вставь свой Telegram ID

LOG_FILE = "logs.json"

def load_logs():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_logs(logs):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

logs = load_logs()

@dp.message()
async def log_message(message: types.Message):
    user = message.from_user
    logs.append({
        "user_id": user.id,
        "name": user.full_name,
        "text": message.text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_logs(logs)

    # обработка команд меню (если совпадают)
    if message.text in ["➕ Добавить таблетку", "📋 Мои таблетки", "📞 Звонок Александру"]:
        return  # эти сообщения уже обрабатываются выше

    await message.answer("🤔 Я тебя не понял. Используй кнопки ниже 👇", reply_markup=main_menu())

@dp.message(F.text == "/logs")
async def show_logs(message: types.Message):
    """Команда для админа — показать все сообщения"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У тебя нет доступа.")
        return

    if not logs:
        await message.answer("Пока нет записанных сообщений.")
    else:
        text = "🗂 Последние сообщения пользователей:\n\n"
        for l in logs[-10:]:  # последние 10 сообщений
            text += f"👤 {l['name']} ({l['user_id']}): {l['text']} — {l['time']}\n"
        await message.answer(text)

# === Запуск ===

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
