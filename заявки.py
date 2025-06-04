import asyncio
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = '8167539174:AAHd1uwdYCVF73PPMoxEg9F-nZkU1QOQ4Q8'
ADMIN_ID = 7019630461
CHANNEL_ID = -1002537727394  # Замените на реальный ID канала (с -100)
CAPTCHA_TIMEOUT = 300  # 5 минут

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Базы данных
users_db = {}
captcha_answers = {}


def generate_captcha(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    correct = "✅ Человек"
    options = [correct, "🤖 Робот", "❓ Не знаю", "🚫 Отмена"]
    random.shuffle(options)

    captcha_answers[user_id] = correct
    users_db[user_id] = {
        "join_time": datetime.now(),
        "attempts": 0,
        "chat_id": CHANNEL_ID  # Явно указываем ID канала
    }

    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(text=option, callback_data=f"captcha_{option.split()[0]}")
    builder.adjust(2)

    text = (
        "🔐 <b>Верификация для вступления</b>\n\n"
        "Выберите правильный вариант:\n"
        f"У вас есть {CAPTCHA_TIMEOUT // 60} минут\n\n"
        "⚠️ Неправильные ответы приведут к запрету доступа"
    )
    return text, builder.as_markup()


@dp.chat_join_request()
async def handle_join(update: types.ChatJoinRequest):
    user = update.from_user

    if user.is_bot:
        await update.decline()
        logger.info(f"Бот {user.full_name} отклонён")
        return

    try:
        text, markup = generate_captcha(user.id)
        await bot.send_message(user.id, text, reply_markup=markup)
        logger.info(f"Капча отправлена {user.full_name} (ID: {user.id})")
    except Exception as e:
        logger.error(f"Ошибка отправки для {user.id}: {e}")
        await update.decline()


@dp.callback_query(F.data.startswith('captcha_'))
async def check_captcha(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    answer = callback.data.replace('captcha_', '')
    user_data = users_db.get(user_id, {})

    # Проверка времени
    if not user_data or (datetime.now() - user_data['join_time']).seconds > CAPTCHA_TIMEOUT:
        await callback.answer("Время вышло!", show_alert=True)
        await decline_user(user_id)
        return

    # Проверка ответа
    if answer == captcha_answers.get(user_id, "").split()[0]:
        await approve_user(user_id, callback)
    else:
        await handle_wrong_answer(user_id, callback)


async def approve_user(user_id: int, callback: types.CallbackQuery):
    try:
        await bot.approve_chat_join_request(
            chat_id=users_db[user_id]["chat_id"],
            user_id=user_id
        )
        await callback.message.edit_text(
            "🎉 <b>Доступ разрешён!</b>\n\n"
            "Теперь вы участник канала.",
            reply_markup=None
        )
        logger.info(f"Пользователь {user_id} принят")
    except Exception as e:
        logger.error(f"Ошибка принятия {user_id}: {e}")
        await callback.answer("Ошибка! Сообщите администратору", show_alert=True)


async def decline_user(user_id: int):
    if user_id in users_db:
        try:
            await bot.decline_chat_join_request(
                chat_id=users_db[user_id]["chat_id"],
                user_id=user_id
            )
            logger.info(f"Пользователь {user_id} отклонён")
        except Exception as e:
            logger.error(f"Ошибка отклонения {user_id}: {e}")
        finally:
            if user_id in users_db:
                del users_db[user_id]
            if user_id in captcha_answers:
                del captcha_answers[user_id]


async def handle_wrong_answer(user_id: int, callback: types.CallbackQuery):
    users_db[user_id]["attempts"] += 1

    if users_db[user_id]["attempts"] >= 3:
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        await decline_user(user_id)
        await callback.message.edit_text(
            "🚫 <b>Доступ запрещён</b>\n\n"
            "Превышено количество попыток.",
            reply_markup=None
        )
    else:
        await callback.answer(f"Неверно! Осталось {3 - users_db[user_id]['attempts']} попытки")
        await callback.message.edit_reply_markup(
            reply_markup=generate_captcha(user_id)[1]
        )


@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    stats = (
        f"📊 Статистика:\n"
        f"• Всего проверок: {len(users_db)}\n"
        f"• Успешных: {sum(1 for u in users_db.values() if u.get('verified'))}\n"
        f"• Активных: {sum(1 for u in users_db.values() if not u.get('verified'))}"
    )
    await message.answer(stats)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    logger.info("=== Запуск бота ===")
    asyncio.run(main())