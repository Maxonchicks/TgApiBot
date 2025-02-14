import sqlite3
import asyncio
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from main import AvitoParse
import logging
from logging.handlers import TimedRotatingFileHandler
import os

bot = AsyncTeleBot('TOKEN')
user_data = {}
tracking_tasks = {}
handler = TimedRotatingFileHandler(
    filename="bot.log",  # Имя файла для логов
    when="midnight",  # Очистка в полночь
    interval=1,  # Интервал в днях
    backupCount=0  # Не сохранять старые логи
)

# Настраиваем формат логов
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)

# Настраиваем основной конфиг для логов
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования
    handlers=[handler]  # Используем обработчик с автоочисткой
)


async def monitor_tracking(user_id, product_name, check_frequency, object_id):
    avito = AvitoParse(
        product_name_search=product_name,
        version_brow=131
    )

    while object_id in tracking_tasks:
        try:
            avito.parse()
            updated_data = avito.updates_product()
            logging.info(f'Информация в телеграмм для пользователя {user_id}: {updated_data}')
            if updated_data:
                for ad_id, ad_data in updated_data.items():
                    title = ad_data[0]  # Название
                    price = ad_data[1]  # Цена
                    description = ad_data[2]  # Описание
                    link = ad_data[3]  # Ссылка
                    images = ad_data[4]  # Кортеж ссылок на изображения

                    # Формируем текст для сообщения
                    message_text = (
                        f"🔔 Найдено новое объявление для *{product_name}*:\n\n"
                        f"*Название:* {title}\n"
                        f"💵 *Цена:* {price} руб.\n\n"
                        f"*Описание:* {description}\n"
                        f"🔗 [Ссылка на объявление]({link})"
                    )

                    # Формируем первую фотографию с текстом
                    media_group = [types.InputMediaPhoto(images[0], caption=message_text, parse_mode='Markdown')]

                    # Добавляем остальные фотографии без текста
                    media_group.extend([types.InputMediaPhoto(image_url) for image_url in images[1:]])

                    # Отправляем группу фотографий с текстом
                    await bot.send_media_group(user_id, media_group)
        except Exception as e:
            logging.error(f"Ошибка при слежке за '{product_name}': {e}")
        await asyncio.sleep(check_frequency * 60)


async def start_tracking():
    conn = sqlite3.connect('tracking.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('SELECT id, user_id, product_name, check_frequency FROM tracking_product')
    tracking_items = cursor.fetchall()
    cursor.close()
    conn.close()

    for item in tracking_items:
        object_id, user_id, product_name, check_frequency = item

        if object_id not in tracking_tasks:
            task = asyncio.create_task(
                monitor_tracking(user_id, product_name, check_frequency, object_id)
            )
            tracking_tasks[object_id] = task


async def stop_tracking(object_id):
    if object_id in tracking_tasks:
        task = tracking_tasks.pop(object_id)
        task.cancel()


@bot.message_handler(commands=['start', 'help'])
async def send_welcome(message):
    conn = sqlite3.connect('tracking.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracking_product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        check_frequency INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')

    user_id = message.chat.id
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Добавить слежку")
    markup.add("Удалить слежку")
    await bot.send_message(user_id, "Добро пожаловать!🙈\nВыберите действие:", reply_markup=markup)


@bot.message_handler(func=lambda msg: msg.text == "Удалить слежку")
async def delete_tracking(message):
    user_id = message.chat.id
    conn = sqlite3.connect('tracking.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('SELECT id, product_name FROM tracking_product WHERE user_id = ?', (user_id,))
    user_trackings = cursor.fetchall()

    if not user_trackings:
        await bot.send_message(user_id, "У вас нет активных объектов слежки.")
        cursor.close()
        conn.close()
        return

    markup = types.InlineKeyboardMarkup()
    for tracking_id, product_name in user_trackings:
        markup.add(types.InlineKeyboardButton(text=product_name, callback_data=f"delete_{tracking_id}"))
    await bot.send_message(user_id, "Выберите слежку для удаления:", reply_markup=markup)

    cursor.close()
    conn.close()


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
async def confirm_deletion(call):
    tracking_id = int(call.data.split("_")[1])
    conn = sqlite3.connect('tracking.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM tracking_product WHERE id = ?', (tracking_id,))
    conn.commit()

    if tracking_id in tracking_tasks:
        await stop_tracking(tracking_id)

    cursor.close()
    conn.close()

    await bot.send_message(call.message.chat.id, "Слежка успешно удалена.")


@bot.message_handler(func=lambda msg: msg.text == "Добавить слежку")
async def add_tracking(message):
    user_id = message.chat.id
    user_data[user_id] = {}
    await bot.send_message(user_id, "Укажите, что будем искать и мониторить (название продукции/услуги):")
    user_data[user_id]['state'] = 'waiting_for_product_name'


@bot.message_handler(func=lambda msg: msg.chat.id in user_data and user_data[msg.chat.id].get('state') == 'waiting_for_product_name')
async def get_product_name(message):
    user_id = message.chat.id
    user_data[user_id]['product_name'] = message.text
    await bot.send_message(user_id, "Как часто проверять новые объявления (в минутах):")
    user_data[user_id]['state'] = 'waiting_for_check_frequency'


@bot.message_handler(func=lambda msg: msg.chat.id in user_data and user_data[msg.chat.id].get('state') == 'waiting_for_check_frequency')
async def get_check_frequency(message):
    user_id = message.chat.id
    try:
        check_frequency = int(message.text)
        user_data[user_id]['check_frequency'] = check_frequency

        conn = sqlite3.connect('tracking.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute(''' 
        INSERT INTO tracking_product (user_id, product_name, check_frequency)
        VALUES (?, ?, ?)
        ''', (user_id, user_data[user_id]['product_name'], check_frequency))
        conn.commit()
        cursor.close()
        conn.close()

        await bot.send_message(user_id, f"Слежка за '{user_data[user_id]['product_name']}' успешно добавлена!")
        user_data.pop(user_id, None)  # Удаляем временные данные пользователя
        await start_tracking()
    except ValueError:
        await bot.send_message(user_id, "Введите корректное число минут.")


async def main():
    if os.path.exists('tracking.db'):
        await start_tracking()
    await bot.polling(none_stop=True)


if __name__ == "__main__":
    asyncio.run(main())
