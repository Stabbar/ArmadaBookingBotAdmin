import os
import re
import threading
from threading import Timer

import telebot

from config import ADMIN_IDS, CONFIG_ADMINS, TELEGRAM_TOKEN, TRAINING_CHAT_ID_STAGING, TRAINING_CHAT_ID_TEST, \
    NOTIFICATION_TO, BIG_CHAT_ID_TEST, TRAINING_CHAT_ID_PROD, BIG_CHAT_ID_PROD
from gsheets import GoogleSheetsClient
from templates_manager import TemplatesManager

#TRAINING_CHAT_ID = TRAINING_CHAT_ID_TEST
#BIG_CHAT_ID = BIG_CHAT_ID_TEST
TRAINING_CHAT_ID = TRAINING_CHAT_ID_PROD
BIG_CHAT_ID = BIG_CHAT_ID_PROD
gsheets = GoogleSheetsClient()
bot = telebot.TeleBot(TELEGRAM_TOKEN)
templates_manager = TemplatesManager()

# Глобальная переменная для хранения состояния ожидания даты
waiting_for_date = {}

# Глобальный словарь для хранения состояния создания тренировки
training_states = {}

# Глобальное хранилище сообщений о тренировках
training_messages_store = {}

# Глобальный словарь для хранения ожидающих подтверждений
pending_reserve_confirmations = {}

def is_admin(user_id):
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS or user_id in CONFIG_ADMINS

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

    templates = templates_manager.list_templates()

    # Убираем default из списка для удаления
    templates = [t for t in templates if t.lower() != 'default']

    if not templates:
        bot.reply_to(message, "❌ Нет шаблонов для удаления (кроме базового).")
        return

    # Создаем инлайн-клавиатуру с шаблонами
    markup = types.InlineKeyboardMarkup()
    for template in templates:
        markup.add(types.InlineKeyboardButton(
            text=template,
            callback_data=f"delete_template_{template}"
        ))

    bot.reply_to(
        message,
        "📋 Выберите шаблон для удаления:",
        reply_markup=markup
    )


# Обработчик кнопок удаления шаблонов
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_template_'))
def confirm_delete_template(call):
    template_name = call.data.replace('delete_template_', '')

    # Создаем клавиатуру подтверждения
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{template_name}"),
        types.InlineKeyboardButton("❌ Нет", callback_data="cancel_delete")
    )

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Вы уверены, что хотите удалить шаблон '{template_name}'?",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)


# Обработчик подтверждения удаления
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def execute_delete_template(call):
    template_name = call.data.replace('confirm_delete_', '')

    if templates_manager.delete_template(template_name):
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Шаблон '{template_name}' успешно удалён!"
        )
    else:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"❌ Не удалось удалить шаблон '{template_name}'"
        )
    bot.answer_callback_query(call.id)


# Обработчик отмены удаления
@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_delete_template(call):
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="❌ Удаление отменено"
    )
    bot.answer_callback_query(call.id)


@bot.message_handler(commands=['listtemplates'])
def list_templates(message):
    templates = templates_manager.list_templates()

    if not templates:
        bot.reply_to(message, "❌ Нет доступных шаблонов.")
        return

    # Создаем инлайн-клавиатуру с шаблонами
    markup = types.InlineKeyboardMarkup()
    for template in templates:
        markup.add(types.InlineKeyboardButton(text=template, callback_data=f"show_template_{template}"))

    bot.reply_to(message, "📋 Доступные шаблоны:", reply_markup=markup)


# Обработчик для кнопок просмотра шаблонов
@bot.callback_query_handler(func=lambda call: call.data.startswith('show_template_'))
def show_template(call):
    template_name = call.data.replace('show_template_', '')
    try:
        template_content = templates_manager.get_template(template_name)
        bot.send_message(
            call.message.chat.id,
            f"📝 Шаблон: <b>{template_name}</b>\n\n{template_content}",
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)


from telebot import types
from datetime import datetime

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


def process_player_limit(message):
    try:
        try:
            player_limit = int(message.text)
            if player_limit < 0:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "❌ Некорректное число. Используйте целое число ≥ 0")
            return

        # Сохраняем лимит в состоянии
        training_states[message.from_user.id]['player_limit'] = player_limit

        # Запрашиваем список игроков (опционально)
        msg = bot.reply_to(message,
                           "📝 Хотите добавить игроков сразу? Отправьте список ФИО (каждое с новой строки)\n"
                           "Или отправьте '0' чтобы пропустить этот шаг")
        bot.register_next_step_handler(msg, process_players_list)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")
        del training_states[message.from_user.id]


def process_players_list(message):
    try:
        user_id = message.from_user.id
        if user_id not in training_states:
            return

        state = training_states[user_id]

        # Если пропускаем добавление игроков
        if message.text.strip() == '0':
            return finalize_training_creation(message)

        # Обрабатываем список игроков
        players_list = []
        unregistered_players = []

        for line in message.text.split('\n'):
            if not line.strip():
                continue

            # Очищаем ФИО от нумерации (1., 2. и т.д.) и спецсимволов
            clean_line = re.sub(r'^\d+\.?\s*', '', line.strip())  # Удаляем нумерацию
            clean_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ\s]', '', clean_line).strip()

            if not clean_name:
                continue

            # Ищем пользователя
            user_data = gsheets.find_user_by_name(clean_name)
            if not user_data or not user_data.get('user_id'):
                unregistered_players.append(clean_name)
                continue

            players_list.append({
                'name': clean_name,
                'user_id': user_data['user_id']
            })

        # Если есть незарегистрированные игроки
        if unregistered_players:
            error_msg = "❌ Эти игроки не зарегистрированы:\n" + "\n".join(unregistered_players)
            bot.reply_to(message, error_msg)
            return None

        # Сохраняем список игроков в состоянии
        state['predefined_players'] = players_list

        # Продолжаем создание тренировки
        finalize_training_creation(message)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")
        if user_id in training_states:
            del training_states[user_id]

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

        msg = bot.reply_to(message, "Введите максимальное количество игроков (число или 0 без лимита):")
        bot.register_next_step_handler(msg, process_player_limit)

    except ValueError as e:
        bot.reply_to(message, f"❌ Неверный формат даты: {str(e)}\nПопробуйте снова:")
        bot.register_next_step_handler(message, process_date_input)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка лимитов: {str(e)}")
        del training_states[user_id]

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


@bot.message_handler(func=lambda m: training_states.get(m.from_user.id, {}).get('step') == 'confirm_creation')
def finalize_training_creation(message):
    try:
        if message.text == "❌ Отмена":
            bot.send_message(
                message.chat.id,
                "❌ Создание тренировки отменено",
                reply_markup=types.ReplyKeyboardRemove()
            )
            del training_states[message.from_user.id]
            return

        state = training_states[message.from_user.id]
        template = templates_manager.get_template(state['template_name'])

        # Формируем текст тренировки
        train_text = template.format(
            date=state['date'],
            location="[место из шаблона]",
            details="[детали из шаблона]"
        ) + f"\n\nЛимит игроков: {state.get('player_limit', 0)}\n\nСписок:\nИгроки:\nВратари:\nРезерв:"

        # Добавляем предопределенных игроков
        if 'predefined_players' in state:
            players = []
            for player in state['predefined_players']:
                players.append(f"{len(players) + 1}. {player['name']}")
                gsheets.update_attendance(
                    player['user_id'],
                    datetime.strptime(state['date'], '%d.%m.%Y %H:%M').date(),
                    present=True,
                    role='player'
                )

            train_text = train_text.replace("Игроки:", f"Игроки:\n" + "\n".join(players))

        # Создаем клавиатуру с кнопкой завершения предзаписи
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("Игрок", callback_data='train_role_player'),
            types.InlineKeyboardButton("Вратарь", callback_data='train_role_goalie')
        )
        markup.row(
            types.InlineKeyboardButton("❌ Отменить запись", callback_data='train_cancel'),
            types.InlineKeyboardButton("✅ Завершить предзапись", callback_data='finish_prereg')
        )

        # Публикуем сообщение в чате предварительной записи
        sent_message = bot.send_message(
            chat_id=TRAINING_CHAT_ID,
            text=train_text,
            reply_markup=markup
        )

        # Сохраняем данные сообщения
        state['pre_reg_message_id'] = sent_message.message_id
        store_training_message(sent_message)

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


# Обработчик кнопки завершения предзаписи
@bot.callback_query_handler(func=lambda call: call.data == 'finish_prereg')
def handle_finish_preregistration(call):
    try:
        # Проверяем права администратора
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Недостаточно прав!", show_alert=True)
            return

        # Получаем текст и данные сообщения
        message_text = call.message.text
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', message_text)
        if not date_match:
            raise ValueError("Не удалось определить дату тренировки")

        date_str = date_match.group(1)

        # Создаем клавиатуру для основного чата
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("Игрок", callback_data='train_role_player'),
            types.InlineKeyboardButton("Вратарь", callback_data='train_role_goalie')
        )
        markup.row(
            types.InlineKeyboardButton("❌ Отменить запись", callback_data='train_cancel')
        )

        # Публикуем сообщение в основном чате
        new_message = bot.send_message(
            chat_id=BIG_CHAT_ID,
            text=message_text,
            reply_markup=markup
        )

        # Сохраняем новое сообщение в хранилище
        store_training_message(new_message)

        # Удаляем сообщение из чата предварительной записи
        bot.delete_message(
            chat_id=TRAINING_CHAT_ID,
            message_id=call.message.message_id
        )

        # Обновляем хранилище - удаляем старое сообщение
        if date_str in training_messages_store:
            training_messages_store[date_str] = [
                msg for msg in training_messages_store[date_str]
                if msg['message_id'] != call.message.message_id
            ]

        bot.answer_callback_query(call.id, "✅ Предзапись завершена, сообщение перемещено в основной чат")

    except Exception as e:
        print(f"Ошибка завершения предзаписи: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при завершении предзаписи")

@bot.message_handler(func=lambda m: m.chat.id == TRAINING_CHAT_ID and "тренировка" in m.text.lower())
def handle_training_message(message):
    """Перехватывает все сообщения о тренировках и сохраняет их"""
    store_training_message(message)


@bot.callback_query_handler(func=lambda call: call.data == 'train_cancel')
def handle_cancel_registration(call):
    global training_date
    try:
        # 1. Получаем информацию о пользователе
        user = call.from_user
        user_data = gsheets.get_user_record(user.id)

        if not user_data or not user_data.get('message'):
            bot.answer_callback_query(call.id, "❌ Ваши данные не найдены", show_alert=True)
            return

        user_message = user_data['message']
        message_id = call.message.message_id
        chat_id = call.message.chat.id

        # 2. Разбираем сообщение о тренировке
        lines = call.message.text.split('\n')
        players = []
        reserves = []
        goalies = []
        other_lines = []
        current_section = None
        found_in_players = False
        found_in_reserves = False
        found_in_goalies = False
        player_number = None
        player_limit = 0

        # 3. Парсим лимит игроков
        for line in lines:
            if "Лимит игроков:" in line:
                try:
                    player_limit = int(line.split(":")[1].strip())
                except:
                    player_limit = 0
                break

        # 4. Анализируем списки участников
        for line in lines:
            if "Игроки:" in line:
                current_section = "players"
                other_lines.append(line)
            elif "Резерв:" in line:
                current_section = "reserves"
                other_lines.append(line)
            elif "Вратари:" in line:
                current_section = "goalies"
                other_lines.append(line)
            elif line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                if user_message in line:
                    # Запоминаем номер игрока
                    player_number = line.split('.')[0].strip()
                    if current_section == "players":
                        found_in_players = True
                    elif current_section == "reserves":
                        found_in_reserves = True
                    elif current_section == "goalies":
                        found_in_goalies = True
                    continue

                if current_section == "players":
                    players.append(line)
                elif current_section == "reserves":
                    reserves.append(line)
                elif current_section == "goalies":
                    goalies.append(line)
            else:
                other_lines.append(line)

        # 5. Проверяем, был ли пользователь записан
        if not (found_in_players or found_in_reserves or found_in_goalies):
            bot.answer_callback_query(call.id, "⚠ Вы не были записаны на эту тренировку", show_alert=True)
            return

        # 6. Получаем дату тренировки
        for line in call.message.text.split('\n'):
            if 'тренировка' in line.lower():
                date_str = line.split('тренировка')[1].strip().split()[0]
                training_date = datetime.strptime(date_str, '%d.%m.%Y')
                break

        # 7. Обработка разных сценариев отмены
        if found_in_players and reserves:
            # Сценарий 1: Отмена основного игрока с резервом
            training_info = {
                'original_message_id': message_id,
                'chat_id': chat_id,
                'training_date': training_date,
                'players_list': players,
                'reserves_list': reserves,
                'goalies_list': goalies,
                'other_lines': other_lines,
                'player_limit': player_limit,
                'reply_markup': call.message.reply_markup
            }
            send_reserve_confirmation(training_info, reserves[0], 0)

            # Пока оставляем списки без изменений (ждем подтверждения)
            new_text = []
            for line in other_lines:
                if line == "Игроки:":
                    new_text.append(line)
                    new_text.extend(players)
                elif line == "Резерв:":
                    new_text.append(line)
                    new_text.extend(reserves)
                elif line == "Вратари:":
                    new_text.append(line)
                    new_text.extend(goalies)
                else:
                    new_text.append(line)
        else:
            # Сценарий 2: Нет резерва или отменяет не основной игрок
            # Формируем новые списки без этого пользователя

            # Пересчитываем нумерацию
            players_renumbered = []
            for i, player in enumerate(players, 1):
                parts = player.split('.', 1)
                players_renumbered.append(f"{i}.{parts[1]}")

            reserves_renumbered = []
            for i, reserve in enumerate(reserves, 1):
                parts = reserve.split('.', 1)
                reserves_renumbered.append(f"{i}.{parts[1]}")

            goalies_renumbered = []
            for i, goalie in enumerate(goalies, 1):
                parts = goalie.split('.', 1)
                goalies_renumbered.append(f"{i}.{parts[1]}")

            # Формируем новое сообщение
            new_text = []
            for line in other_lines:
                if line == "Игроки:":
                    new_text.append(line)
                    new_text.extend(players_renumbered)
                elif line == "Резерв:":
                    new_text.append(line)
                    new_text.extend(reserves_renumbered)
                elif line == "Вратари:":
                    new_text.append(line)
                    new_text.extend(goalies_renumbered)
                else:
                    new_text.append(line)

        # 8. Обновляем сообщение о тренировке
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text='\n'.join(new_text),
            reply_markup=call.message.reply_markup
        )

        # 9. Обновляем посещаемость
        gsheets.update_attendance(user.id, training_date, present=False)

        # 10. Уведомляем пользователя
        bot.answer_callback_query(call.id, "✅ Ваша запись отменена!")

        player_name = user_data.get('message', user_data.get('message', 'Неизвестный игрок'))
        section_name = 'основном составе' if found_in_players else 'резерве' if found_in_reserves else 'вратарях'

        # Формируем текст уведомления с номером игрока
        notification_text = (
            f"⚠️ Игрок отменил запись на тренировку\n"
            f"Дата: {training_date.strftime('%d.%m.%Y')}\n"
            f"Игрок: {player_name}\n"
            f"Был в: {section_name}\n"
            f"Номер в списке: {player_number}"  # Добавлен номер игрока
        )
        send_admin_notification(notification_text)

    except Exception as e:
        print(f"Ошибка: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка сервера")


def send_reserve_confirmation(training_info, reserve_player, reserve_index):
    """Отправляет запрос подтверждения резервисту"""
    try:
        # Удаляем "(резерв)" из имени игрока перед поиском
        clean_player_name = reserve_player.split('.', 1)[1].strip().replace('(резерв)', '').strip()
        reserve_user_id = gsheets.get_user_id_by_name(clean_player_name)

        if not reserve_user_id:
            print(f"Не найден user_id для резервиста: {clean_player_name}")
            return

        # Создаем клавиатуру подтверждения
        markup = types.InlineKeyboardMarkup()
        confirm_btn = types.InlineKeyboardButton(
            text="✅ Подтвердить переход",
            callback_data=f"reserve_confirm_{training_info['original_message_id']}"
        )
        markup.add(confirm_btn)

        # Отправляем сообщение
        sent_msg = bot.send_message(
            reserve_user_id,
            f"Вы первый в резерве на тренировку {training_info['training_date'].strftime('%d.%m.%Y')}.\n"
            "Хотите перейти в основной состав?",
            reply_markup=markup
        )

        # Сохраняем информацию о запросе
        pending_reserve_confirmations[training_info['original_message_id']] = {
            'training_info': training_info,
            'reserve_index': reserve_index,
            'reserve_user_id': reserve_user_id,
            'reserve_player_name': clean_player_name,  # Сохраняем очищенное имя
            'confirmation_msg_id': sent_msg.message_id,
            'timestamp': datetime.now()
        }

        # Устанавливаем таймер на 1 час
        Timer(3600, check_reserve_confirmation, [training_info['original_message_id']]).start()

    except Exception as e:
        print(f"Ошибка отправки подтверждения резервисту: {e}")


def check_reserve_confirmation(message_id):
    """Проверяет подтверждение через 1 час"""
    if message_id not in pending_reserve_confirmations:
        return

    confirmation_data = pending_reserve_confirmations[message_id]
    training_info = confirmation_data['training_info']
    reserve_index = confirmation_data['reserve_index']

    # Если подтверждения не было, пробуем следующего резервиста
    if len(training_info['reserves_list']) > reserve_index + 1:
        send_reserve_confirmation(training_info, training_info['reserves_list'][reserve_index + 1], reserve_index + 1)

    # Удаляем старый запрос
    pending_reserve_confirmations.pop(message_id, None)


@bot.callback_query_handler(func=lambda call: call.data.startswith('reserve_confirm_'))
def handle_reserve_confirmation(call):
    try:
        message_id = int(call.data.split('_')[-1])
        if message_id not in pending_reserve_confirmations:
            bot.answer_callback_query(call.id, "❌ Запрос устарел")
            return

        confirmation_data = pending_reserve_confirmations.pop(message_id)
        training_info = confirmation_data['training_info']
        reserve_player = training_info['reserves_list'][confirmation_data['reserve_index']]
        reserve_user_id = confirmation_data['reserve_user_id']

        # Обновляем списки
        players = training_info['players_list']
        reserves = training_info['reserves_list']

        # Удаляем из резерва и добавляем в основной состав
        reserves.pop(confirmation_data['reserve_index'])
        players.append(f"{len(players) + 1}. {reserve_player.split('.', 1)[1].strip().replace('(резерв)', '')}")

        # Пересчитываем нумерацию
        players_renumbered = [f"{i}.{p.split('.', 1)[1]}" for i, p in enumerate(players, 1)]
        reserves_renumbered = [f"{i}.{r.split('.', 1)[1]}" for i, r in enumerate(reserves, 1)]

        # Формируем новое сообщение
        new_text = []
        for line in training_info['other_lines']:
            if line == "Игроки:":
                new_text.append(line)
                new_text.extend(players_renumbered)
            elif line == "Резерв:":
                new_text.append(line)
                new_text.extend(reserves_renumbered)
            elif line == "Вратари:":
                new_text.append(line)
                new_text.extend(training_info['goalies_list'])
            else:
                new_text.append(line)

        # Обновляем сообщение о тренировке
        bot.edit_message_text(
            chat_id=training_info['chat_id'],
            message_id=training_info['original_message_id'],
            text='\n'.join(new_text),
            reply_markup=training_info['reply_markup']
        )

        # Обновляем посещаемость
        gsheets.update_attendance(
            reserve_user_id,
            training_info['training_date'],
            present=True,
            role='player'
        )

        # Уведомляем резервиста
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="✅ Вы были переведены в основной состав!"
        )

        notification_text = (
            f"🔄 Игрок перешел из резерва в основной состав\n"
            f"Дата: {training_info['training_date'].strftime('%d.%m.%Y')}\n"
            f"Игрок: {reserve_player}"
        )
        send_admin_notification(notification_text)

    except Exception as e:
        print(f"Ошибка обработки подтверждения: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка сервера")


def store_training_message(message):
    """Сохраняет сообщение о тренировке с учетом чата"""
    try:
        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', message.text)
        if date_match:
            date_str = date_match.group(1)
            if date_str not in training_messages_store:
                training_messages_store[date_str] = []

            training_messages_store[date_str].append({
                'chat_id': message.chat.id,  # Сохраняем ID чата
                'message_id': message.message_id,
                'text': message.text
            })
    except Exception as e:
        print(f"Ошибка сохранения сообщения: {e}")


def find_training_message(chat_id, training_date):
    """Ищет сообщение о тренировке по дате в истории чата"""
    try:
        # Формируем строку для поиска (дата в формате сообщения)
        search_date = training_date.strftime('%d.%m.%Y')

        # Получаем последние 100 сообщений (можно увеличить при необходимости)
        messages = bot.get_chat_history(chat_id, limit=100)

        for msg in messages:
            if msg.text and search_date in msg.text and "тренировка" in msg.text.lower():
                return {
                    'chat_id': chat_id,
                    'message_id': msg.message_id,
                    'text': msg.text
                }
        return None
    except Exception as e:
        print(f"Ошибка поиска сообщения: {e}")
        return None


def find_all_training_messages(chat_id, training_date):
    """Находит все сообщения о тренировке (основное и возможно дополнения)"""
    try:
        search_date = training_date.strftime('%d.%m.%Y')
        messages = bot.get_chat_history(chat_id, limit=200)  # Увеличиваем лимит
        result = []

        for msg in messages:
            if msg.text and search_date in msg.text and "тренировка" in msg.text.lower():
                result.append({
                    'chat_id': chat_id,
                    'message_id': msg.message_id,
                    'text': msg.text
                })
        return result
    except Exception as e:
        print(f"Ошибка поиска сообщений: {e}")
        return []


def is_training_message(msg, training_date):
    """Проверяет что сообщение соответствует тренировке на указанную дату"""
    if not msg.text:
        return False

    date_str = training_date.strftime('%d.%m.%Y')

    # Проверяем что это сообщение о тренировке и содержит нужную дату
    return ("тренировка" in msg.text.lower() and
            date_str in msg.text and
            any(word in msg.text.lower() for word in ["список", "игроки", "вратари"]))



@bot.message_handler(commands=['canceltrain'])
def start_cancel_training(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    # Запрашиваем дату у администратора
    msg = bot.reply_to(message, "📅 Введите дату тренировки для отмены в формате ДД.ММ.ГГГГ:")

    # Регистрируем следующий шаг для этого пользователя
    bot.register_next_step_handler(msg, process_cancel_date)


def process_cancel_date(message):
    try:
        user_id = message.from_user.id
        if not is_admin(user_id):
            bot.reply_to(message, "⛔ Недостаточно прав!")
            return

        date_str = message.text.strip()
        training_date = datetime.strptime(date_str, '%d.%m.%Y').date()
        current_date = datetime.now().date()

        if training_date <= current_date:
            bot.reply_to(message, "❌ Можно отменять только будущие тренировки!")
            return

        # 1. Удаляем сообщения из хранилища
        messages_to_delete = training_messages_store.get(date_str, [])
        success_count = 0

        for msg_data in messages_to_delete:
            try:
                bot.delete_message(msg_data['chat_id'], msg_data['message_id'])
                success_count += 1
            except Exception as e:
                print(f"Не удалось удалить сообщение {msg_data['message_id']}: {e}")

        # 2. Удаляем данные из таблицы
        if gsheets.cancel_training(training_date):
            result_msg = f"⛔️ Тренировка на {date_str} отменена!"
            if success_count < len(messages_to_delete):
                result_msg += f"\n(Удалено {success_count} из {len(messages_to_delete)} сообщений)"
            bot.reply_to(message, result_msg)
        else:
            bot.reply_to(message, "❌ Не удалось отменить тренировку в таблице или на тренировку никто не записался")

    except ValueError as e:
        bot.reply_to(message, f"❌ Ошибка формата даты: {e}\nПожалуйста, введите дату в формате ДД.ММ.ГГГГ")
        # Повторно запрашиваем дату при ошибке
        msg = bot.reply_to(message, "📅 Введите дату тренировки для отмены в формате ДД.ММ.ГГГГ:")
        bot.register_next_step_handler(msg, process_cancel_date)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

# Команда для проверки прав
@bot.message_handler(commands=['admin'])
def check_admin(message):
    if is_admin(message.from_user.id):
        bot.reply_to(message, "🛡 Вы администратор!")
    else:
        bot.reply_to(message, "⛔ У вас нет прав администратора")


def update_admin_ids(new_admin_id):
    """
    Обновляет массив ADMIN_IDS в config.py
    :param new_admin_id: ID нового администратора
    :return: True если успешно, False если ошибка
    """
    try:
        # Читаем текущий файл config.py
        with open('config.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Находим строку с объявлением ADMIN_IDS
        pattern = r'ADMIN_IDS\s*=\s*\[([^\]]*)\]'
        match = re.search(pattern, content)

        if not match:
            raise ValueError("Не найдено объявление ADMIN_IDS в config.py")

        # Получаем текущие ID
        current_ids = [int(id_.strip()) for id_ in match.group(1).split(',') if id_.strip()]

        # Проверяем, не добавлен ли уже этот ID
        if new_admin_id in current_ids:
            return True  # Уже есть, считаем успехом

        # Добавляем новый ID
        current_ids.append(new_admin_id)

        # Формируем новую строку
        new_ids_str = ', '.join(str(id_) for id_ in current_ids)
        new_content = re.sub(pattern, f'ADMIN_IDS = [{new_ids_str}]', content)

        # Создаем временный файл для безопасной записи
        temp_file = 'config_temp.py'
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Заменяем оригинальный файл
        os.replace(temp_file, 'config.py')

        # Обновляем текущий массив ADMIN_IDS
        global ADMIN_IDS
        ADMIN_IDS = current_ids

        return True

    except Exception as e:
        print(f"Ошибка при обновлении ADMIN_IDS: {e}")
        return False


@bot.message_handler(commands=['addadmin'])
def add_admin_command(message):
    """Добавление пользователя в администраторы"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "ℹ Ответьте на сообщение пользователя, которого хотите сделать администратором")
        return

    target_user = message.reply_to_message.from_user
    target_user_id = target_user.id

    # Проверки
    if target_user_id == message.from_user.id:
        bot.reply_to(message, "❌ Вы уже администратор!")
        return

    if target_user_id in ADMIN_IDS:
        bot.reply_to(message, f"ℹ Пользователь @{target_user.username} уже администратор")
        return

    if target_user_id in CONFIG_ADMINS:
        bot.reply_to(message, "❌ Этот пользователь является системным администратором")
        return

    try:
        if update_admin_ids(target_user_id):
            bot.reply_to(message, f"✅ @{target_user.username} добавлен в администраторы!\n")
        else:
            bot.reply_to(message, "❌ Не удалось обновить список администраторов")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


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


def remove_admin_from_config(admin_id):
    """
    Удаляет admin_id из массива ADMIN_IDS в config.py
    :param admin_id: ID администратора для удаления
    :return: True если успешно, False если ошибка
    """
    try:
        # Читаем текущий файл config.py
        with open('config.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Находим строку с объявлением ADMIN_IDS
        pattern = r'ADMIN_IDS\s*=\s*\[([^\]]*)\]'
        match = re.search(pattern, content)

        if not match:
            raise ValueError("Не найдено объявление ADMIN_IDS в config.py")

        # Получаем текущие ID (исключая удаляемый)
        current_ids = [int(id_.strip()) for id_ in match.group(1).split(',') if
                       id_.strip() and int(id_.strip()) != admin_id]

        # Проверяем, был ли этот ID в списке
        if len(current_ids) == len([int(id_.strip()) for id_ in match.group(1).split(',') if id_.strip()]):
            return False  # ID не был найден в списке

        # Формируем новую строку
        new_ids_str = ', '.join(str(id_) for id_ in current_ids)
        new_content = re.sub(pattern, f'ADMIN_IDS = [{new_ids_str}]', content)

        # Создаем временный файл для безопасной записи
        temp_file = 'config_temp.py'
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Заменяем оригинальный файл
        os.replace(temp_file, 'config.py')

        # Обновляем текущий массив ADMIN_IDS
        global ADMIN_IDS
        ADMIN_IDS = current_ids

        return True

    except Exception as e:
        print(f"Ошибка при обновлении ADMIN_IDS: {e}")
        return False


@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message):
    """Удаление пользователя из администраторов"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "ℹ Ответьте на сообщение администратора, которого хотите разжаловать")
        return

    target_user = message.reply_to_message.from_user
    target_user_id = target_user.id

    # Проверки
    if target_user_id == message.from_user.id:
        bot.reply_to(message, "❌ Вы не можете снять права с себя!")
        return

    if target_user_id not in ADMIN_IDS:
        bot.reply_to(message, f"ℹ Пользователь @{target_user.username} не является администратором")
        return

    if target_user_id in CONFIG_ADMINS:
        bot.reply_to(message, "❌ Этот администратор указан в конфигурации бота!")
        return

    try:
        if remove_admin_from_config(target_user_id):
            bot.reply_to(message, f"✅ @{target_user.username} больше не администратор!")
        else:
            bot.reply_to(message, f"❌ Пользователь @{target_user.username} не найден в списке администраторов")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


@bot.message_handler(commands=['register'])
def handle_register(message):
    try:
        user = message.from_user

        # Проверка регистрации
        if gsheets.is_user_exists(user.id):
            reply = bot.reply_to(message, "⚠️ Вы уже зарегистрированы!")
            # Удаляем только в групповых чатах
            if message.chat.type != 'private':
                threading.Timer(300, lambda: bot.delete_message(message.chat.id, reply.message_id)).start()
            return

        # Проверка типа чата
        if message.chat.type != 'private':
            markup = types.InlineKeyboardMarkup()
            url_button = types.InlineKeyboardButton(
                text="Перейти в личный чат с ботом",
                url=f"tg://resolve?domain={bot.get_me().username}"
            )
            markup.add(url_button)

            sent_msg = bot.reply_to(
                message,
                "⚠️ Пожалуйста, продолжите регистрацию в личных сообщениях с ботом",
                reply_markup=markup
            )
            # Удаляем через 5 минут только в групповых чатах
            threading.Timer(300, lambda: bot.delete_message(message.chat.id, sent_msg.message_id)).start()
            return

        # Процесс регистрации в ЛС
        msg = bot.send_message(
            message.chat.id,
            "Введите ваши Фамилию и Имя через пробел:",
            reply_markup=types.ForceReply()
        )
        bot.register_next_step_handler(msg, lambda m: save_registration(m, user))
        gsheets.clear_cache()

    except Exception as e:
        error_msg = bot.reply_to(message, f"❌ Ошибка: {e}")
        # Удаляем ошибку только в групповых чатах
        if message.chat.type != 'private':
            threading.Timer(300, lambda: bot.delete_message(message.chat.id, error_msg.message_id)).start()


def save_registration(message, user):
    try:
        full_name = message.text.strip()
        if len(full_name.split()) < 2:
            error_msg = bot.reply_to(message, "❌ Требуется ввести и Фамилию и Имя")
            # Сообщения в ЛС не удаляем
            if message.chat.type != 'private':
                threading.Timer(300, lambda: bot.delete_message(message.chat.id, error_msg.message_id)).start()
            return

        if gsheets.add_record(user, full_name):
            bot.reply_to(message, f"✅ Данные сохранены:\nИмя: {full_name}")
        else:
            error_msg = bot.reply_to(message, "❌ Ошибка при сохранении!")
            if message.chat.type != 'private':
                threading.Timer(300, lambda: bot.delete_message(message.chat.id, error_msg.message_id)).start()

    except Exception as e:
        error_msg = bot.reply_to(message, f"❌ Ошибка: {e}")
        if message.chat.type != 'private':
            threading.Timer(300, lambda: bot.delete_message(message.chat.id, error_msg.message_id)).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith('train_role_'))
def handle_training_button(call):
    global training_date
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
        reserves = []
        goalies = []
        other_lines = []
        current_section = None
        player_limit = 0

        # Парсим лимит игроков
        for line in lines:
            if "Лимит игроков:" in line:
                try:
                    player_limit = int(line.split(":")[1].strip())
                except:
                    player_limit = 0
                break

        # Обрабатываем все строки сообщения
        for line in lines:
            if "Игроки:" in line:
                current_section = "players"
                other_lines.append(line)
            elif "Резерв:" in line:
                current_section = "reserves"
                other_lines.append(line)
            elif "Вратари:" in line:
                current_section = "goalies"
                other_lines.append(line)
            elif line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
                if current_section == "players":
                    players.append(line)
                elif current_section == "reserves":
                    reserves.append(line)
                elif current_section == "goalies":
                    goalies.append(line)
            else:
                other_lines.append(line)

        # Проверяем дублирование во всех списках
        all_participants = players + reserves + goalies
        if any(user_message in p for p in all_participants):
            bot.answer_callback_query(call.id, f"⚠ Вы уже записаны на тренировку!")
            return

        # Обработка записи в зависимости от роли
        if role == "Игрок":
            if player_limit > 0 and len(players) >= player_limit:
                # Записываем в резерв
                new_number = len(reserves) + 1
                reserves.append(f"{new_number}. {user_message} (резерв)")
                response_text = "✅ Вы записаны в резерв!"
            else:
                # Записываем в основной состав
                new_number = len(players) + 1
                players.append(f"{new_number}. {user_message}")
                response_text = "✅ Вы записаны как игрок!"
        else:
            # Для вратарей лимитов нет
            new_number = len(goalies) + 1
            goalies.append(f"{new_number}. {user_message}")
            response_text = "✅ Вы записаны как вратарь!"

        # Формируем новое сообщение
        new_text = []
        for line in other_lines:
            if line == "Игроки:":
                new_text.append(line)
                new_text.extend(players)
            elif line == "Резерв:":
                new_text.append(line)
                new_text.extend(reserves)
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

        # Получаем дату тренировки из сообщения
        for line in call.message.text.split('\n'):
            if 'тренировка' in line.lower():
                date_str = line.split('тренировка')[1].strip().split()[0]
                training_date = datetime.strptime(date_str, '%d.%m.%Y')
                break

        # Обновляем посещаемость
        role_for_sheet = 'player' if call.data == 'train_role_player' else 'goalie'
        gsheets.update_attendance(call.from_user.id, training_date, present=True)

        bot.answer_callback_query(call.id, response_text)

    except Exception as e:
        print(f"Ошибка: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка сервера")

#Подписка на уведомления. Если включена - при отмене записи на тренировку информируем подписавшихся админов
@bot.message_handler(commands=['subnotify'])
def subscribe_notifications(message):
    """Подписка администратора на уведомления"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        admin_id = message.from_user.id

        # Читаем текущий config.py
        with open('config.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем/добавляем список NOTIFICATION_TO
        if 'NOTIFICATION_TO =' not in content:
            content += '\nNOTIFICATION_TO = []\n'

        # Ищем текущее определение массива
        pattern = r'NOTIFICATION_TO\s*=\s*\[([^\]]*)\]'
        match = re.search(pattern, content)

        if not match:
            raise ValueError("Не найдено объявление NOTIFICATION_TO в config.py")

        # Получаем текущие ID
        current_ids = [int(id_.strip()) for id_ in match.group(1).split(',') if id_.strip()]

        # Проверяем, не подписан ли уже
        if admin_id in current_ids:
            bot.reply_to(message, "ℹ Вы уже подписаны на уведомления")
            return

        # Добавляем ID
        current_ids.append(admin_id)
        new_ids_str = ', '.join(str(id_) for id_ in current_ids)
        new_content = re.sub(pattern, f'NOTIFICATION_TO = [{new_ids_str}]', content)

        # Сохраняем изменения
        with open('config.py', 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Обновляем текущий массив
        global NOTIFICATION_TO
        NOTIFICATION_TO = current_ids

        bot.reply_to(message, "✅ Вы подписались на уведомления об изменениях записей")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")


@bot.message_handler(commands=['unsubnotify'])
def unsubscribe_notifications(message):
    """Отписка от уведомлений"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Недостаточно прав!")
        return

    try:
        admin_id = message.from_user.id

        with open('config.py', 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'NOTIFICATION_TO\s*=\s*\[([^\]]*)\]'
        match = re.search(pattern, content)

        if not match:
            bot.reply_to(message, "ℹ Вы не подписаны на уведомления")
            return

        current_ids = [int(id_.strip()) for id_ in match.group(1).split(',') if id_.strip()]

        if admin_id not in current_ids:
            bot.reply_to(message, "ℹ Вы не подписаны на уведомления")
            return

        # Удаляем ID
        current_ids.remove(admin_id)
        new_ids_str = ', '.join(str(id_) for id_ in current_ids)
        new_content = re.sub(pattern, f'NOTIFICATION_TO = [{new_ids_str}]', content)

        with open('config.py', 'w', encoding='utf-8') as f:
            f.write(new_content)

        global NOTIFICATION_TO
        NOTIFICATION_TO = current_ids

        bot.reply_to(message, "✅ Вы отписались от уведомлений")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {str(e)}")

# Функция для отправки уведомлений
def send_admin_notification(message_text):
    """Отправляет уведомление всем подписанным админам"""
    for admin_id in NOTIFICATION_TO:
        try:
            bot.send_message(admin_id, message_text)
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")

@bot.message_handler(commands=['help'])
def show_help(message):
    help_text = """
📌 Основные команды для всех пользователей:

🏋️‍♂️ Запись на тренировки
Нажмите кнопку "Игрок" или "Вратарь" под сообщением о тренировке

Для отмены записи нажмите "❌ Отменить запись"

📝 Регистрация в системе
/register - Зарегистрироваться в системе (требуется один раз)

ℹ Помощь
/help - Показать список доступных команд



🔐 Команды для администраторов:

📋 Управление шаблонами тренировок
/addtemplate - Добавить новый шаблон
Формат:
/addtemplate  
Название шаблона   
Текст сообщения (дату указывать в формате {date})

Строки в конце сообщения: 
"Список красавчиков: 
Игроки: 
Вратари:
Резерв:"

Зашиты в код как константа и будут указаны в конце сообщения для любого шаблона. Отдельно добавлять их не нужно

Пример:
/addtemplate  
Зимний  
Объявляется тренировка в ФОК Зимний. Дата тренировки: {date}
Брать СВЕТЛЫЕ и ТЕМНЫЕ свитера

/edittemplate - Изменить существующий шаблон
/deletetemplate - Удалить шаблон
/listtemplates - Показать список доступных шаблонов

🏟 Создание тренировки
/createtrain - Создать новую тренировку (пошаговый процесс)

❌ Отмена тренировки
/canceltrain - Отменить тренировку (пошаговый процесс)

👥 Управление администраторами
/addadmin - Добавить администратора (ответом на сообщение пользователя)
/removeadmin - Удалить администратора (ответом на сообщение)
/admin - Проверить свои права
/users - Просмотреть список зарегистрированных пользователей

🕒 Форматы дат и времени
Дата тренировки: ДД.ММ.ГГГГ (например: 15.12.2025)

Дата и время: ДД.ММ.ГГГГ ЧЧ:ММ (например: 15.12.2025 18:00)

⚠️ Ограничения
Отменять можно только будущие тренировки

Администраторы, указанные в конфигурации бота, не могут быть удалены

Нельзя снять права администратора с самого себя

🔄 Логика работы
При создании тренировки бот использует шаблоны

Игроки могут записываться как в основной состав, так и в резерв (при достижении лимита)

Все изменения синхронизируются с Google Таблицей

Для получения помощи по конкретной команде обратитесь к администратору.

Исходники бота:
https://github.com/Stabbar/ArmadaBookingBotAdmin/tree/master

Конфиг и креды гугл-дока сам соберешь
"""
    bot.reply_to(message, help_text)



def cleanup_messages_store():
    """Очищает хранилище от старых сообщений"""
    global training_messages_store

    current_date = datetime.now().date()
    old_dates = []

    for date_str in training_messages_store:
        try:
            msg_date = datetime.strptime(date_str, '%d.%m.%Y').date()
            if msg_date < current_date:
                old_dates.append(date_str)
        except:
            continue

    for date_str in old_dates:
        del training_messages_store[date_str]

    # Повторяем каждые 24 часа
    Timer(86400, cleanup_messages_store).start()


# Запускаем очистку при старте
cleanup_messages_store()

if __name__ == '__main__':
    print("Бот запущен. Ожидание команд")
    bot.polling()