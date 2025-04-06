import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import GOOGLE_SHEETS_CREDENTIALS_FILE, SPREADSHEET_ID, WORKSHEET_NAME, ADMIN_IDS


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

    def is_admin(self, user_id):
        """Проверяет, является ли пользователь администратором"""
        if user_id in ADMIN_IDS:
            return True

        try:
            # Ищем в столбце is_admin (индекс 4)
            cell = self.worksheet.find(str(user_id), in_column=1)
            if cell:
                is_admin = self.worksheet.cell(cell.row, 6).value
                return is_admin == 'TRUE'
        except:
            return False
        return False

    def add_admin(self, admin_id, target_user_id):
        """Добавляет администратора"""
        if not self.is_admin(admin_id):
            return False

        try:
            cell = self.worksheet.find(str(target_user_id), in_column=1)
            if cell:
                self.worksheet.update_cell(cell.row, 6, 'TRUE')
                return True
        except:
            return False
        return False

    def remove_admin(self, admin_id, target_user_id):
        """Удаляет права администратора"""
        if not self.is_admin(admin_id):
            return False

        try:
            cell = self.worksheet.find(str(target_user_id), in_column=1)
            if cell:
                # Проверяем, что это не конфигурационный админ
                if target_user_id in ADMIN_IDS:
                    return False

                self.worksheet.update_cell(cell.row, 6, 'FALSE')
                return True
        except:
            return False
        return False

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
            existing_ids = self.worksheet.col_values(1)
            return str(user_id) in existing_ids
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