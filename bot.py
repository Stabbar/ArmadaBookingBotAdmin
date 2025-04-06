import telebot
from telebot import types
from gsheets import GoogleSheetsClient
from config import TELEGRAM_TOKEN, ADMIN_IDS

gsheets = GoogleSheetsClient()
bot = telebot.TeleBot(TELEGRAM_TOKEN)


def is_admin(user_id):
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS or gsheets.is_admin(user_id)


# Команда для проверки прав
@bot.message_handler(commands=['admin'])
def check_admin(message):
    if is_admin(message.from_user.id):
        bot.reply_to(message, "🛡 Вы администратор!")
    else:
        bot.reply_to(message, "⛔ У вас нет прав администратора")


# Команда для добавления администратора
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "ℹ Ответьте на сообщение пользователя, которого хотите сделать администратором")
        return

    target_user_id = message.reply_to_message.from_user.id
    if gsheets.add_admin(admin_id, target_user_id):
        bot.reply_to(message, f"✅ Пользователь @{message.reply_to_message.from_user.username} теперь администратор!")
    else:
        bot.reply_to(message, "❌ Не удалось назначить администратора")


# Команда для просмотра всех пользователей (только для админов)
@bot.message_handler(commands=['users'])
def list_users(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        users = gsheets.worksheet.get_all_records()
        response = "📊 Зарегистрированные пользователи:\n\n"
        for user in users:
            admin_flag = " (admin)" if user.get('is_admin') == 'TRUE' else ""
            response += f"👤 {user.get('full_name')}{admin_flag}\n"
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")


@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    admin_id = message.from_user.id
    if not is_admin(admin_id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "ℹ Ответьте на сообщение администратора, которого хотите разжаловать")
        return

    target_user_id = message.reply_to_message.from_user.id

    # Нельзя удалить себя
    if target_user_id == admin_id:
        bot.reply_to(message, "❌ Вы не можете снять права с себя!")
        return

    # Нельзя удалить конфигурационных админов
    if target_user_id in ADMIN_IDS:
        bot.reply_to(message, "❌ Этот администратор указан в конфигурации бота!")
        return

    if gsheets.remove_admin(admin_id, target_user_id):
        bot.reply_to(message, f"✅ Пользователь @{message.reply_to_message.from_user.username} больше не администратор!")
    else:
        bot.reply_to(message, "❌ Не удалось снять права администратора")

@bot.message_handler(commands=['register'])
def handle_register(message):
    try:
        user = message.from_user

        if gsheets.is_user_exists(user.id):
            bot.reply_to(message, "⚠️ Вы уже зарегистрированы!")
            return

        # Запрос ФИО
        msg = bot.send_message(
            message.chat.id,
            "Введите ваши Фамилию и Имя через пробел:",
            reply_markup=types.ForceReply()
        )
        bot.register_next_step_handler(msg, lambda m: save_registration(m, user))

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")


def save_registration(message, user):
    try:
        full_name = message.text.strip()
        if len(full_name.split()) < 2:
            raise ValueError("Требуется ввести и Фамилию и Имя")

        if gsheets.add_record(user, full_name):
            bot.reply_to(message, f"✅ Данные сохранены:\nID: {user.id}\nИмя: {full_name}")
        else:
            bot.reply_to(message, "❌ Ошибка при сохранении!")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")


if __name__ == '__main__':
    print("Бот запущен. Ожидание команды /register...")
    bot.polling(none_stop=True)