import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from config import GOOGLE_SHEETS_CREDENTIALS_FILE, SPREADSHEET_ID, WORKSHEET_NAME


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
        """Инициализация листа с обновлёнными заголовками"""
        try:
            self.spreadsheet = self.client.open_by_key(SPREADSHEET_ID)
            try:
                self.worksheet = self.spreadsheet.worksheet(WORKSHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=WORKSHEET_NAME,
                    rows=1000,
                    cols=10
                )
                # Новые заголовки в snake_case
                self.worksheet.append_row([
                    "user_id",
                    "telegram_name",
                    "full_name",
                    "message",
                    "timestamp"
                ])

            # Проверяем заголовки
            current_headers = self.worksheet.row_values(1)
            expected_headers = ["user_id", "telegram_name", "full_name", "message", "timestamp"]
            if current_headers != expected_headers:
                self._update_headers(expected_headers)

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