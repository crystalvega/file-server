# Corporate Temporary File Server (Корпоративное хранилище временных файлов)

Сервис временного защищенного обмена большими файлами для корпоративной почты (аналог Apple Mail Drop, Google Drive attachment links, Thunderbird Filelink) с прямой интеграцией в **Bulwark Webmail** и проксированием через **Traefik**.

Решает проблему разрастания базы данных Stalwart (blob-хранилища) и лимитов SMTP на размер вложений: большие файлы (видео, архивы, чертежи) загружаются на файловый сервер, хранятся ограниченное время (до 28 дней) и автоматически удаляются, а в тело письма вставляется защищенная ссылка с кодом доступа.

---

## 🚀 Основные возможности

1. **Защита ссылкой и PIN-кодом:**
   - Каждая загрузка получает уникальный криптографический 32-значный идентификатор (`/files/{upload_id}`).
   - Доступ защищен 6-значным цифровым PIN-кодом (генерируется автоматически или задается вручную).
   - Хеширование паролей с солью через **PBKDF2-HMAC-SHA256** (100 000 итераций).
   - **Защита от перебора (Brute-force protection):** блокировка на 15 минут при 5 неверных попытках ввода PIN-кода.
2. **Пакетная загрузка нескольких файлов:**
   - Если пользователь прикрепляет 2, 3 и более файлов, они группируются под **одну общую ссылку и один PIN-код**.
   - На странице скачивания доступно как скачивание каждого файла по отдельности, так и **скачивание всех файлов одним архивом (.ZIP)** на лету без создания промежуточных копий на диске (потоковый ZIP).
3. **Автоматический срок жизни (TTL 28 дней):**
   - Максимальный срок хранения — **28 дней**.
   - Фоновый планировщик регулярно проверяет срок жизни и безвозвратно удаляет истекшие файлы и директории с диска.
4. **Легковесный интерфейс:**
   - Полностью автономный чистый веб-интерфейс на русском языке (без внешних зависимостей и CDN).
   - Адаптирован под смартфоны и ПК.
   - Страница ручной загрузки с функцией Drag-and-Drop и мгновенной генерацией готового блока для вставки в письмо.
5. **REST API для интеграции:**
   - Простой endpoint `POST /api/upload` для почтового клиента Bulwark.

---

## 📡 REST API

### 1. Загрузка файлов (для Bulwark)
```http
POST /api/upload
Content-Type: multipart/form-data
```

**Параметры:**
- `files`: Один или несколько файлов (`multipart/form-data`)
- `pin` *(опционально)*: 6-значный PIN (если не передан — сгенерируется автоматически)
- `ttl_days` *(опционально)*: Срок хранения в днях (по умолчанию `28`, максимум `28`)

**Пример ответа:**
```json
{
  "success": true,
  "upload_id": "c8a419eb7b3749e7bdf4083d09a74421",
  "url": "https://mail.szma-inform.ru/files/c8a419eb7b3749e7bdf4083d09a74421",
  "pin": "749201",
  "expires_at": "2026-12-16T12:00:00Z",
  "ttl_days": 28,
  "total_size": 157286400,
  "formatted_size": "150.0 МБ",
  "files_count": 2,
  "files": [
    {
      "id": "f_1",
      "name": "Проект_СЗМА_v2.dwg",
      "size": 52428800,
      "formatted_size": "50.0 МБ",
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "id": "f_2",
      "name": "Видео_объекта.mp4",
      "size": 104857600,
      "formatted_size": "100.0 МБ",
      "sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"
    }
  ]
}
```

### 2. Шаблон вставки в письмо
При успешной загрузке Bulwark генерирует и вставляет в текст письма блок:
```text
📎 Вложенные файлы (доступны до 16.12.2026):
  • Проект_СЗМА_v2.dwg (50.0 МБ)
  • Видео_объекта.mp4 (100.0 МБ)

👉 Ссылка для скачивания: https://mail.szma-inform.ru/files/c8a419eb7b3749e7bdf4083d09a74421
🔑 Код доступа: 749201
```

---

## 🛠 Развертывание в Docker Compose

Добавьте сервис в `/opt/stalwart-core/docker-compose.yml`:

```yaml
  file-server:
    image: git.szma-inform.ru/mail.local/file-server:latest
    container_name: file-server
    restart: unless-stopped
    environment:
      - PUBLIC_BASE_URL=https://mail.${DOMAIN}
      - URL_PREFIX=/files
      - DEFAULT_TTL_DAYS=28
      - MAX_TTL_DAYS=28
      - MAX_FILE_SIZE_MB=10240
    volumes:
      - file_server_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 5s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.files.rule=Host(`mail.${DOMAIN}`) && (PathPrefix(`/files`) || PathPrefix(`/file-server`))"
      - "traefik.http.routers.files.entrypoints=websecure"
      - "traefik.http.routers.files.tls=true"
      - "traefik.http.services.files.loadbalancer.server.port=8000"
      - "com.centurylinklabs.watchtower.enable=true"

volumes:
  file_server_data:
    name: file_server_data
```

---

## ⚙️ Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `PUBLIC_BASE_URL` | *(из Host)* | Базовый публичный URL (например `https://mail.szma-inform.ru`) |
| `URL_PREFIX` | `/files` | Префикс URL для страниц и API |
| `DEFAULT_TTL_DAYS` | `28` | Срок хранения файлов по умолчанию |
| `MAX_TTL_DAYS` | `28` | Максимально допустимый срок хранения |
| `MAX_FILE_SIZE_MB` | `10240` | Максимальный размер одного файла (МБ) |
| `DATA_DIR` | `/data` | Каталог хранения файлов и метаданных |
| `RATE_LIMIT_ATTEMPTS` | `5` | Количество попыток ввода PIN до блокировки |
| `RATE_LIMIT_LOCKOUT_MINUTES` | `15` | Длительность блокировки при неверном PIN (минут) |
