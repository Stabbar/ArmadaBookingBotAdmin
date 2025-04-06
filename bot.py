import telebot
from telebot import types
from gsheets import GoogleSheetsClient
from config import TELEGRAM_TOKEN

# Инициализация
gsheets = GoogleSheetsClient()
bot = telebot.TeleBot(TELEGRAM_TOKEN)


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