import telebot
from telebot import types
from datetime import datetime
from gsheets import GoogleSheetsClient
from config import TELEGRAM_TOKEN, ADMIN_IDS, TRAINING_CHAT_ID
from templates_manager import TemplatesManager

gsheets = GoogleSheetsClient()
bot = telebot.TeleBot(TELEGRAM_TOKEN)

templates_manager = TemplatesManager()

# Глобальный словарь для хранения состояния создания тренировки
training_states = {}

@bot.message_handler(commands=['addtemplate'])
def add_template(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        parts = message.text.split('\n', 2)
        if len(parts) < 3:
            raise ValueError(
                "Неверный формат. Используйте:\n"
                "/addtemplate\n"
                "название\n"
                "текст шаблона\n\n"
                "Пример:\n/addtemplate\nлетний\nЛетняя тренировка {date}\nМесто: {location}"
            )

        name = parts[1].strip()
        template_text = parts[2].strip()

        if templates_manager.add_template(name, template_text):
            bot.reply_to(message, f"✅ Шаблон '{name}' успешно добавлен!")
        else:
            bot.reply_to(message, f"❌ Шаблон '{name}' уже существует")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['edittemplate'])
def edit_template(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        parts = message.text.split('\n', 2)
        if len(parts) < 3:
            raise ValueError(
                "Неверный формат. Используйте:\n"
                "/edittemplate\n"
                "название\n"
                "новый текст\n\n"
                "Пример:\n/edittemplate\nзимний\nНовый текст шаблона"
            )

        name = parts[1].strip()
        new_text = parts[2].strip()

        if templates_manager.edit_template(name, new_text):
            bot.reply_to(message, f"✅ Шаблон '{name}' успешно обновлён!")
        else:
            bot.reply_to(message, f"❌ Шаблон '{name}' не найден")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['deletetemplate'])
def delete_template(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        name = message.text.split(' ', 1)[1].strip()
        if templates_manager.delete_template(name):
            bot.reply_to(message, f"✅ Шаблон '{name}' удалён!")
        else:
            bot.reply_to(message, f"❌ Не удалось удалить шаблон '{name}'")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listtemplates'])
def list_templates(message):
    templates = templates_manager.list_templates()
    response = "📋 Доступные шаблоны:\n\n" + "\n".join(f"• {name}" for name in templates)
    bot.reply_to(message, response)


from telebot import types
from datetime import datetime

# Глобальный словарь для хранения состояния создания тренировки
training_states = {}


@bot.message_handler(commands=['createtrain'])
def start_training_creation(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    # Получаем список шаблонов
    templates = templates_manager.list_templates()

    if not templates:
        bot.reply_to(message, "❌ Нет доступных шаблонов. Сначала создайте шаблон через /addtemplate")
        return

    # Создаем клавиатуру с шаблонами
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for template in templates:
        markup.add(types.KeyboardButton(template))

    # Запрашиваем выбор шаблона
    msg = bot.send_message(
        message.chat.id,
        "📋 Какой шаблон выбрать?",
        reply_markup=markup
    )

    # Сохраняем состояние
    training_states[message.from_user.id] = {
        'step': 'select_template',
        'chat_id': message.chat.id
    }

    bot.register_next_step_handler(msg, process_template_selection)


def process_template_selection(message):
    user_id = message.from_user.id
    if user_id not in training_states:
        return

    template_name = message.text.strip()

    # Проверяем существование шаблона
    if template_name not in templates_manager.list_templates():
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.")
        del training_states[user_id]
        return

    # Сохраняем выбранный шаблон
    training_states[user_id]['template_name'] = template_name
    training_states[user_id]['step'] = 'enter_date'

    # Запрашиваем дату
    msg = bot.send_message(
        message.chat.id,
        "📅 Укажите дату и время тренировки в формате ДД.ММ.ГГГГ ЧЧ:ММ\n"
        "Например: 15.04.2025 19:30",
        reply_markup=types.ReplyKeyboardRemove()
    )

    bot.register_next_step_handler(msg, process_date_input)


def process_date_input(message):
    user_id = message.from_user.id
    if user_id not in training_states:
        return

    try:
        # Парсим дату
        train_date = datetime.strptime(message.text, '%d.%m.%Y %H:%M')
        if train_date < datetime.now():
            raise ValueError("Дата должна быть в будущем")

        # Сохраняем дату
        training_states[user_id]['date'] = train_date.strftime('%d.%m.%Y %H:%M')
        training_states[user_id]['step'] = 'confirm_creation'

        # Получаем шаблон
        template = templates_manager.get_template(training_states[user_id]['template_name'])

        # Форматируем сообщение (пока без даты)
        preview_text = template.format(
            date="[дата будет здесь]",
            location="[место из шаблона]",
            details="[детали из шаблона]"
        ).replace("[дата будет здесь]", training_states[user_id]['date'])

        # Создаем клавиатуру подтверждения
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton("✅ Создать"), types.KeyboardButton("❌ Отмена"))

        # Показываем превью
        bot.send_message(
            message.chat.id,
            f"📝 Превью сообщения:\n\n{preview_text}\n\n"
            "Подтвердите создание тренировки:",
            reply_markup=markup
        )

    except ValueError as e:
        bot.reply_to(message, f"❌ Неверный формат даты: {str(e)}\nПопробуйте снова:")
        bot.register_next_step_handler(message, process_date_input)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")
        del training_states[user_id]


@bot.message_handler(func=lambda m: training_states.get(m.from_user.id, {}).get('step') == 'confirm_creation')
def finalize_training_creation(message):
    try:
        state = training_states[message.from_user.id]
        template = templates_manager.get_template(state['template_name'])

        train_text = template.format(
            date=state['date'],
            location="[место из шаблона]",
            details="[детали из шаблона]"
        ) + "\n\nСписок красавчиков:\nИгроки:\nВратари:"

        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("Игрок", callback_data='train_role_player'),
            types.InlineKeyboardButton("Вратарь", callback_data='train_role_goalie')
        )

        bot.send_message(
            chat_id=TRAINING_CHAT_ID,
            text=train_text,
            reply_markup=markup
        )

        bot.send_message(
            message.chat.id,
            f"✅ Тренировка создана по шаблону '{state['template_name']}'!",
            reply_markup=types.ReplyKeyboardRemove()
        )

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")
    finally:
        if message.from_user.id in training_states:
            del training_states[message.from_user.id]

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


@bot.callback_query_handler(func=lambda call: call.data.startswith('train_role_'))
def handle_training_button(call):
    try:
        user = call.from_user
        role = "Игрок" if call.data == 'train_role_player' else "Вратарь"

        # Проверяем регистрацию
        if not gsheets.is_user_exists(user.id):
            bot.answer_callback_query(
                call.id,
                "⛔ Вы не зарегистрированы!\nИспользуйте /register",
                show_alert=True
            )
            return

        # Получаем данные из таблицы
        user_data = gsheets.get_user_record(user.id)
        if not user_data or not user_data.get('message'):
            bot.answer_callback_query(
                call.id,
                "❌ Ваши данные не найдены",
                show_alert=True
            )
            return

        user_message = user_data['message']

        # Разбираем текущее сообщение
        lines = call.message.text.split('\n')
        players = []
        goalies = []
        other_lines = []
        current_section = None

        for line in lines:
            if "Игроки:" in line:
                current_section = "players"
                other_lines.append(line)
            elif "Вратари:" in line:
                current_section = "goalies"
                other_lines.append(line)
            elif line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                if current_section == "players":
                    players.append(line)
                elif current_section == "goalies":
                    goalies.append(line)
            else:
                other_lines.append(line)

        # Проверяем дублирование
        all_participants = players + goalies
        if any(user_message in p for p in all_participants):
            bot.answer_callback_query(call.id, f"⚠ Вы уже записаны как {role}!")
            return

        # Добавляем участника в нужный список
        if role == "Игрок":
            players.append(f"{len(players) + 1}. {user_message}")
        else:
            goalies.append(f"{len(goalies) + 1}. {user_message}")

        # Формируем новое сообщение
        new_text = []
        for line in other_lines:
            if line == "Игроки:":
                new_text.append(line)
                new_text.extend(players)
            elif line == "Вратари:":
                new_text.append(line)
                new_text.extend(goalies)
            else:
                new_text.append(line)

        # Обновляем сообщение
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='\n'.join(new_text),
            reply_markup=call.message.reply_markup
        )

        bot.answer_callback_query(call.id, f"✅ Вы записаны как {role}!")

    except Exception as e:
        print(f"Ошибка: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка сервера")

@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = """
📋 Команды управления шаблонами:

/addtemplate - Добавить шаблон
/edittemplate - Редактировать шаблон
/deletetemplate - Удалить шаблон
/listtemplates - Список шаблонов

📌 Создание тренировки:
/createtrain [шаблон]
параметр: значение
параметр: значение

Пример:
/createtrain зимний
date: 15.12.2025 18:00
location: Ледовая арена
details: Коньки, перчатки
"""
    bot.reply_to(message, help_text)

if __name__ == '__main__':
    print("Бот запущен. Ожидание команд")
    bot.polling(none_stop=True)