import re
from typing import Dict, Any
from fastapi import Request

SUPPORTED_LOCALES = ["en", "ru"]
DEFAULT_LOCALE = "en"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # General & Base
        "app_name": "Corporate File Storage",
        "app_subtitle": "Secure email attachment transfer",
        "brand_title": "Bulwark Mail Drop",
        "page_title_default": "Corporate File Storage",
        "footer_text": "© 2026 Bulwark Mail • Temporary files stored for up to 28 days",
        "theme_auto": "Automatic (system)",
        "theme_light": "Light theme",
        "theme_dark": "Dark theme",
        "theme_label": "Switch theme",
        "lang_label": "Language",

        # Index page
        "index_title": "Bulwark Mail Drop File Storage",
        "index_subtitle": "Corporate service for large file attachments",
        "index_alert_title": "Restricted Access:",
        "index_alert_desc": "File uploads to this server are restricted to authorized personnel via the Bulwark Webmail plugin.",
        "index_how_to_send": "How to send files:",
        "index_step_1": "Open the email composer in <strong>Bulwark Webmail</strong>.",
        "index_step_2": "Click the <strong>«File Server»</strong> button in the bottom toolbar or in the attachment 📎 menu.",
        "index_step_3": "Select files of any size (up to 10 GB) — the download link and 6-digit PIN code will be automatically inserted into the email.",
        "index_got_link_title": "Received a file link?",
        "index_got_link_desc": "Follow the link from the email (e.g. <code>{prefix}/[file_code]</code>) and enter the 6-digit access code (PIN).",
        "index_go_to_mail": "Go to Bulwark Webmail",

        # Download page
        "download_page_title": "Download Attachments",
        "download_title_auth": "Attached Files",
        "download_title_unauth": "Access Code Verification",
        "download_subtitle_auth": "Files are available for secure download",
        "download_subtitle_unauth": "Enter the 6-digit PIN from the received email to access attachments",
        "meta_files_count": "Files:",
        "meta_total_size": "Total size:",
        "meta_expires": "Expires:",
        "btn_download_file": "Download",
        "btn_download_all": "Download all files as archive (.ZIP)",
        "btn_verify_pin": "Verify PIN",
        "pin_placeholder": "000000",
        "error_invalid_pin": "Invalid PIN code. Please try again.",
        "error_locked": "Too many failed attempts. Access locked for {minutes} minutes.",
        "error_expired": "The files have expired and are no longer available.",

        # Error page
        "error_page_title": "Files Not Available",
        "error_not_found_title": "Files Not Found",
        "error_not_found_desc": "The temporary retention period (28 days) has expired, or the link is incorrect.",
        "btn_back_home": "Back to Home Page",

        # API Messages
        "api_unauthorized": "Access denied. Invalid or missing API key.",
        "api_no_files": "No files provided for upload.",
        "api_file_too_large": "File '{filename}' exceeds maximum allowed size ({max_mb} MB).",
        "api_invalid_ttl": "Retention period must be between 1 and {max_days} days.",
        "api_invalid_pin": "PIN must be exactly 6 digits.",
        "api_upload_not_found": "Upload bundle not found or expired.",
    },
    "ru": {
        # General & Base
        "app_name": "Корпоративное хранилище файлов",
        "app_subtitle": "Безопасная передача вложений к письмам",
        "brand_title": "Bulwark Mail Drop",
        "page_title_default": "Корпоративное хранилище файлов",
        "footer_text": "© 2026 Bulwark Mail • Временные файлы хранятся до 28 дней",
        "theme_auto": "Автоматически (по системе)",
        "theme_light": "Светлая тема",
        "theme_dark": "Тёмная тема",
        "theme_label": "Переключение темы",
        "lang_label": "Язык",

        # Index page
        "index_title": "Хранилище файлов Bulwark Mail Drop",
        "index_subtitle": "Корпоративный сервис передачи больших вложений",
        "index_alert_title": "Защита от стороннего доступа:",
        "index_alert_desc": "Загрузка файлов на данный сервер разрешена исключительно авторизованным сотрудникам через плагин почты Bulwark.",
        "index_how_to_send": "Как отправить файлы:",
        "index_step_1": "Откройте редактор письма в <strong>Bulwark Webmail</strong>.",
        "index_step_2": "Нажмите кнопку <strong>«Файловый сервер»</strong> в нижней панели или выберите пункт в меню скрепки 📎.",
        "index_step_3": "Выберите файлы любого размера (до 10 ГБ) — ссылка и 6-значный PIN-код автоматически добавятся в письмо.",
        "index_got_link_title": "Получили ссылку на файл?",
        "index_got_link_desc": "Перейдите по прямой ссылке из письма (вида <code>{prefix}/[код_файла]</code>) и введите 6-значный код доступа (PIN).",
        "index_go_to_mail": "Перейти в почту Bulwark",

        # Download page
        "download_page_title": "Скачивание вложений",
        "download_title_auth": "Вложенные файлы",
        "download_title_unauth": "Вход по коду доступа",
        "download_subtitle_auth": "Файлы доступны для безопасного скачивания",
        "download_subtitle_unauth": "Для доступа к вложениям введите 6-значный PIN из полученного письма",
        "meta_files_count": "Файлов:",
        "meta_total_size": "Общий объем:",
        "meta_expires": "Истекает:",
        "btn_download_file": "Скачать",
        "btn_download_all": "Скачать все файлы архивом (.ZIP)",
        "btn_verify_pin": "Подтвердить код",
        "pin_placeholder": "000000",
        "error_invalid_pin": "Неверный PIN-код. Попробуйте снова.",
        "error_locked": "Слишком много неудачных попыток. Доступ заблокирован на {minutes} мин.",
        "error_expired": "Срок хранения файлов истек.",

        # Error page
        "error_page_title": "Файлы недоступны",
        "error_not_found_title": "Файлы не найдены",
        "error_not_found_desc": "Срок временного хранения файлов (28 дней) истек, либо указана неверная ссылка.",
        "btn_back_home": "На главную страницу",

        # API Messages
        "api_unauthorized": "Доступ запрещен. Неверный или отсутствует API-ключ.",
        "api_no_files": "Не переданы файлы для загрузки.",
        "api_file_too_large": "Размер файла '{filename}' превышает максимально допустимый ({max_mb} МБ).",
        "api_invalid_ttl": "Срок хранения должен быть от 1 до {max_days} дней.",
        "api_invalid_pin": "PIN-код должен состоять ровно из 6 цифр.",
        "api_upload_not_found": "Файлы не найдены или срок их хранения истек.",
    }
}

class LocalizationDict(dict):
    """Dictionary wrapper that supports formatting kwargs."""
    def __init__(self, locale: str):
        self.locale = locale
        base = TRANSLATIONS.get(DEFAULT_LOCALE, {})
        target = TRANSLATIONS.get(locale, {})
        merged = {**base, **target}
        super().__init__(merged)

    def __call__(self, key: str, **kwargs) -> str:
        text = self.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

def detect_locale(request: Request) -> str:
    # 1. Explicit query parameter
    lang_param = request.query_params.get("lang")
    if lang_param and lang_param.lower() in SUPPORTED_LOCALES:
        return lang_param.lower()

    # 2. Cookies (Bulwark / Next.js / Custom)
    for cookie_key in ["lang", "locale", "NEXT_LOCALE", "bulwark_locale"]:
        val = request.cookies.get(cookie_key)
        if val:
            val_clean = val.lower().split("-")[0].split("_")[0]
            if val_clean in SUPPORTED_LOCALES:
                return val_clean

    # 3. Referer header from Bulwark (e.g. /webmail/ru/... or /webmail/en/...)
    referer = request.headers.get("referer", "")
    if referer:
        match = re.search(r"/(?:webmail/)?([a-zA-Z]{2})(?:/|$)", referer)
        if match:
            ref_lang = match.group(1).lower()
            if ref_lang in SUPPORTED_LOCALES:
                return ref_lang

    # 4. Accept-Language header
    accept_lang = request.headers.get("accept-language", "")
    if accept_lang:
        for part in accept_lang.split(","):
            code = part.split(";")[0].strip().lower().split("-")[0]
            if code in SUPPORTED_LOCALES:
                return code

    return DEFAULT_LOCALE

def get_translations(request: Request) -> LocalizationDict:
    locale = detect_locale(request)
    return LocalizationDict(locale)
