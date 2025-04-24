from datetime import datetime, timedelta
import functools
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import SPREADSHEET_ID, WORKSHEET_NAME, ATTENDANCE_SHEET_NAME

GOOGLE_SHEETS_CREDENTIALS_FILE = 'credentials.json'

class GoogleSheetsClient:
    def __init__(self):
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(
            GOOGLE_SHEETS_CREDENTIALS_FILE, self.scope)
        self.client = gspread.authorize(self.creds)
        self._init_worksheet()
        self._user_cache = {}
        self._name_to_id_cache = {}
        self._last_cache_update = datetime.min

    def clear_cache(self):
        """Очищает все кэши"""
        self._user_cache = {}
        self._name_to_id_cache = {}
        self._last_cache_update = datetime.min
        # Очищаем LRU кэши декорированных функций
        self.get_user_record.cache_clear()
        self.get_user_id_by_name.cache_clear()

    def _check_cache_expiry(self):
        """Проверяет истек ли срок действия кэша (5 минут)"""
        if datetime.now() - self._last_cache_update > timedelta(minutes=1):
            self.clear_cache()

    def _init_worksheet(self):
        """Инициализация листа с новыми полями"""
        try:
            self.spreadsheet = self.client.open_by_key(SPREADSHEET_ID)
            try:
                self.worksheet = self.spreadsheet.worksheet(WORKSHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=WORKSHEET_NAME,
                    rows=50,
                    cols=10
                )
                self.worksheet.append_row([
                    "user_id",
                    "telegram_name",
                    "full_name",
                    "message",
                    "registration_date",
                    "is_admin"
                ])

        except Exception as e:
            raise Exception(f"Ошибка инициализации таблицы: {str(e)}")

    def _update_headers(self, new_headers):
        """Обновление заголовков таблицы"""
        header_range = f"A1:{chr(65 + len(new_headers) - 1)}1"
        self.worksheet.update(header_range, [new_headers])

    @staticmethod
    def get_full_name(user):
        """Объединяет имя и фамилию пользователя"""
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        return f"{first_name} {last_name}".strip()

    def is_user_exists(self, user_id):
        """Проверяет существование пользователя по ID"""
        try:
            # Ищем в первом столбце (user_id)
            cell = self.worksheet.find(str(user_id), in_column=1)
            return cell
        except Exception as e:
            print(f"Ошибка при проверке пользователя: {e}")
            return False

    def add_record(self, user, message_text):
        """Добавляет запись в таблицу"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            row = [
                user.id,
                user.username or "",
                self.get_full_name(user),
                message_text,
                timestamp
            ]
            self.worksheet.append_row(row)
            return True
        except Exception as e:
            print(f"Ошибка при добавлении записи: {e}")
            return False

    @functools.lru_cache(maxsize=1000)  # Дополнительное кэширование на уровне функции
    def get_user_record(self, user_id):
        """Возвращает запись пользователя по ID с кэшированием"""
        try:
            self._check_cache_expiry()

            # Проверяем кэш
            if str(user_id) in self._user_cache:
                return self._user_cache[str(user_id)]

            # Если нет в кэше, ищем в таблице
            cell = self.worksheet.find(str(user_id))
            if cell:
                record = {
                    'user_id': self.worksheet.cell(cell.row, 1).value,
                    'telegram_name': self.worksheet.cell(cell.row, 2).value,
                    'full_name': self.worksheet.cell(cell.row, 3).value,
                    'message': self.worksheet.cell(cell.row, 4).value
                }

                # Сохраняем в кэш
                self._user_cache[str(user_id)] = record
                self._last_cache_update = datetime.now()
                return record

            return None
        except Exception as e:
            print(f"Ошибка при поиске пользователя: {e}")
            return None

    def invalidate_user_cache(self, user_id=None):
        """Инвалидирует кэш для конкретного пользователя или полностью"""
        if user_id is None:
            self.clear_cache()
        else:
            self._user_cache.pop(str(user_id), None)
            self.get_user_record.cache_clear()  # Очищаем LRU кэш

    @functools.lru_cache(maxsize=1000)
    def get_user_id_by_name(self, message):
        """Возвращает user_id по ФИО пользователя с кэшированием"""
        try:
            self._check_cache_expiry()

            # Проверяем кэш
            if message in self._name_to_id_cache:
                return self._name_to_id_cache[message]

            # Если нет в кэше, ищем в таблице
            cell = self.worksheet.find(message)
            if cell:
                # Предполагаем, что ФИО находится в 3 колонке (как в get_user_record)
                if cell.col != 4:
                    # Если нашли не в той колонке, ищем правильно
                    for row in self.worksheet.get_all_values():
                        if len(row) > 3 and row[3] == message:
                            user_id = row[0] if len(row) > 0 else None
                            if user_id:
                                # Сохраняем в кэш
                                self._name_to_id_cache[message] = user_id
                                self._last_cache_update = datetime.now()
                                return user_id
                    return None

                # Если нашли в правильной колонке
                user_id = self.worksheet.cell(cell.row, 1).value  # 1 колонка - user_id
                if user_id:
                    # Сохраняем в кэш
                    self._name_to_id_cache[message] = user_id
                    self._last_cache_update = datetime.now()
                    return user_id

            return None
        except Exception as e:
            print(f"Ошибка при поиске user_id по ФИО: {e}")
            return None

    def get_attendance_sheet(self):
        """Возвращает лист с графиком посещений, создает если не существует"""
        try:
            spreadsheet = self.client.open_by_key(SPREADSHEET_ID)
            try:
                worksheet = spreadsheet.worksheet(ATTENDANCE_SHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(
                    title=ATTENDANCE_SHEET_NAME,
                    rows=100,
                    cols=20
                )
                # Создаем заголовки
                worksheet.update('A1:B1', [['ФИО', 'Всего']])
            return worksheet
        except Exception as e:
            print(f"Ошибка доступа к таблице посещений: {e}")
            raise

    def update_attendance(self, user_id, training_date, present=True, role=None):
        """Обновляет график посещений с учетом роли (player/goalie)"""
        try:
            # Открываем таблицу посещений
            worksheet = self.get_attendance_sheet()
            # Получаем данные
            records = worksheet.get_all_records()
            headers = worksheet.row_values(1)
            date_str = training_date.strftime('%d.%m.%Y')

            # Проверяем/добавляем столбец с датой
            if date_str not in headers:
                worksheet.insert_cols([[date_str]], len(headers))
                headers = worksheet.row_values(1)

            # Ищем пользователя
            user_data = self.get_user_record(user_id)
            if not user_data:
                return False

            user_name = user_data['message']
            user_row = None

            for i, row in enumerate(worksheet.get_all_values(), 1):
                if row and row[0] == user_name:
                    user_row = i
                    break

            # Если пользователь не найден - добавляем
            if not user_row:
                new_row = [user_name] + ['' for _ in range(len(headers) - 1)]
                worksheet.append_row(new_row)
                user_row = len(worksheet.get_all_values())

            # Обновляем ячейку с учетом роли
            col_idx = headers.index(date_str) + 1
            current_value = worksheet.cell(user_row, col_idx).value

            # Формируем новое значение
            if not present:
                new_value = ''
            elif role == 'goalie':
                new_value = 'G'  # Отметка для вратарей
            else:
                new_value = '1'  # Обычное посещение

            # Обновляем только если:
            # - Нет текущей записи и нужно поставить посещение
            # - Или нужно убрать посещение
            if (not current_value and present) or (current_value and not present):
                worksheet.update_cell(user_row, col_idx, new_value)

            # Обновляем "Всего" и "Вратари"
            total_col = len(headers)
            if "Всего" not in headers[-1]:
                worksheet.update_cell(1, total_col, "Всего")
                worksheet.update_cell(1, total_col + 1, "Вратари")

            # Считаем статистику
            row_values = worksheet.row_values(user_row)
            total_visits = sum(1 for val in row_values[1:-2] if val == '1')
            goalie_visits = sum(1 for val in row_values[1:-2] if val == 'G')

            worksheet.update_cell(user_row, total_col, total_visits)
            worksheet.update_cell(user_row, total_col + 1, goalie_visits)

            return True

        except Exception as e:
            print(f"Ошибка обновления посещаемости: {e}")
            return False

#TODO: Подсчет тренировок слетает при отмене. Минорно, но потом надо будет поправить
    def cancel_training(self, training_date):
        """Удаляет данные о тренировке из таблицы"""
        try:
            worksheet = self.get_attendance_sheet()
            headers = worksheet.row_values(1)
            date_str = training_date.strftime('%d.%m.%Y')

            if date_str not in headers:
                return False  # Нет такой тренировки

            # Находим индекс столбца
            col_idx = headers.index(date_str) + 1  # +1 т.к. индексы с 1

            # Удаляем столбец со сдвигом влево
            worksheet.delete_columns(col_idx)

            # Обновляем "Всего" для всех пользователей
            self.recalculate_totals(worksheet)

            return True

        except Exception as e:
            print(f"Ошибка отмены тренировки: {e}")
            return False


    def recalculate_totals(self, worksheet):
        """Пересчитывает графу 'Всего'"""
        try:
            records = worksheet.get_all_records()
            headers = worksheet.row_values(1)

            if 'Всего' not in headers:
                return

            total_col = headers.index('Всего') + 1
            all_values = worksheet.get_all_values()

            for i, row in enumerate(all_values[1:], start=2):  # Пропускаем заголовок
                if not row:
                    continue

                # Считаем отметки посещения (✅)
                visits = sum(1 for val in row[1:total_col - 1] if val == '✅')
                worksheet.update_cell(i, total_col, visits)

        except Exception as e:
            print(f"Ошибка пересчета итогов: {e}")