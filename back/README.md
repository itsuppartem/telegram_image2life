# Ozhivlyator Backend

## Краткое описание

Ozhivlyator Backend – это микросервис, обеспечивающий бэкенд-логику для приложения, которое "оживляет" детские рисунки с помощью AI-генерации изображений. Сервис управляет пользователями, генерациями изображений, платежами и предоставляет API для взаимодействия с клиентскими приложениями.

## Архитектура и технологии
! Дисклеймер, в сервисе используется система из ключей апи, с официальным бесплатным лимитом запросов в сутки в 1500 запросов. Не рекомендуется повторять такой подход.


Сервис построен на базе Python с использованием асинхронного фреймворка FastAPI.

*   **Язык и фреймворк:**
    *   Python 3.10+
    *   FastAPI 0.100.0+
    *   *Обоснование:* FastAPI выбран за высокую производительность, встроенную асинхронность (эффективно для I/O-bound операций, таких как запросы к внешним API и базам данных), автоматическую валидацию данных через Pydantic и генерацию OpenAPI документации. Python — за обширную экосистему библиотек и удобство разработки.

*   **Базы данных:**
    *   **MongoDB** (c использованием `motor` 3.0+): Основное хранилище данных для пользовательских профилей, информации о генерациях, платежах и других связанных сущностей.
        *   *Обоснование:* Гибкость схемы NoSQL MongoDB хорошо подходит для хранения документов с переменной структурой (например, пользовательские данные, история транзакций). `motor` обеспечивает асинхронный доступ к MongoDB, что соответствует общей асинхронной архитектуре приложения.
    *   **Redis** (c использованием `redis.asyncio` 4.5+): Используется для управления квотами запросов к Google Gemini API (отслеживание лимитов RPM/RPD), а также может быть использован для кеширования и других задач, требующих быстрого доступа к данным.
        *   *Обоснование:* Redis — это высокопроизводительное in-memory хранилище, идеальное для операций, критичных к задержкам, таких как проверка и обновление счетчиков API-лимитов.

*   **Ключевые библиотеки:**
    *   `Pydantic` 2.0+: Для валидации данных, настроек и сериализации.
    *   `Uvicorn` 0.23.0+: ASGI-сервер для запуска FastAPI приложения.
    *   `httpx` 0.25.0+: Асинхронный HTTP-клиент для взаимодействия с внешними API (Google Gemini, YooKassa).
    *   `Pillow (PIL)` 9.0+: Для предварительной обработки загружаемых изображений.
    *   `python-dotenv`: Для управления конфигурацией через переменные окружения.
    *   `google-generativeai`: Клиентская библиотека для взаимодействия с Google Gemini API.
    *   `yookassa`: Клиентская библиотека для интеграции с платежной системой YooKassa.

*   **Внешние сервисы:**
    *   **Google Gemini API:** Для генерации изображений на основе пользовательских рисунков.
    *   **YooKassa API:** Для обработки онлайн-платежей.

*   **API протокол:** REST.

*   **Аутентификация:** Внутренний API-ключ. Запросы к защищенным эндпоинтам должны содержать заголовок `api-key` с валидным ключом.

## Настройка окружения

Для работы сервиса необходимо определить следующие переменные окружения. Создайте файл `.env` в корне проекта со следующим содержимым:

```dotenv
# MongoDB Configuration
MONGO_URI="mongodb://user:password@host:port/your_db"
MONGO_DB_NAME="ozhivlyator_db"

# Google Gemini API Keys (comma-separated if multiple)
GEMINI_API_KEYS_STR="your_gemini_api_key_1,your_gemini_api_key_2"

# Internal API Key for securing service endpoints
API_KEY="your_very_strong_and_secret_internal_api_key"

# YooKassa Configuration
YOOKASSA_SHOP_ID="your_yookassa_shop_id"
YOOKASSA_SECRET_KEY="your_yookassa_secret_key"

# Telegram Bot Information (used for return URLs, etc.)
TELEGRAM_BOT_USERNAME="YourTelegramBotUsername"

# Redis Configuration
REDIS_URL="redis://localhost:6379/0"

# Logging (optional, defaults to enabled in code if var is missing)
# LOGGING_ENABLED="True"
```

## Примеры использования

### 1. Создание нового пользователя

Этот эндпоинт регистрирует нового пользователя в системе.

**Запрос:**

```bash
curl -X POST "http://localhost:8000/users" \
-H "Content-Type: application/json" \
-H "api-key: your_very_strong_and_secret_internal_api_key" \
-d '{
  "chat_id": 123456789,
  "username": "newuser",
  "referral_code": "ref_987654321",
  "advertising_source": "src_ads_campaign_01"
}'
```

**Ответ (успешное создание):**

```json
{
  "chat_id": 123456789,
  "username": "newuser",
  "ozhivashki": 1,
  "generation_count": 0,
  "last_generation_time": null,
  "registered_at": "2024-03-15T12:00:00.000000",
  "referral_code": "ref_123456789",
  "referred_by": 987654321,
  "referral_bonus_claimed": false,
  "first_generation_time": null,
  "daily_bonus_claimed_today": false,
  "daily_bonus_streak": 0,
  "discount_offered": false,
  "last_activity_time": "2024-03-15T12:00:00.000000",
  "advertising_source": "src_ads_campaign_01",
  "yookassa_payments": {}
}
```

### 2. Генерация изображения

Этот эндпоинт принимает изображение от пользователя, отправляет его в Google Gemini API для обработки и возвращает сгенерированные изображения.

**Запрос:**

Для отправки файла используется `multipart/form-data`.

```bash
curl -X POST "http://localhost:8000/generate" \
-H "api-key: your_very_strong_and_secret_internal_api_key" \
-F "chat_id=123456789" \
-F "image=@/path/to/your/drawing.png"
```

**Ответ (успешная генерация):**

*Примечание: `base64_encoded_image_string...` являются плейсхолдерами для реальных base64-строк изображений. Количество бонусных изображений и `new_balance` зависят от логики сервиса (например, первая генерация, бонусы за серию).*

```json
{
  "main_images": [
    "base64_encoded_image_string_1",
    "base64_encoded_image_string_2",
    "base64_encoded_image_string_3",
    "base64_encoded_image_string_4"
  ],
  "bonus_images": [
    "base64_encoded_image_string_bonus_1",
    "base64_encoded_image_string_bonus_2"
  ],
  "ozhivashki_spent": 1,
  "new_balance": 0
}
```

### 3. Получение информации о пользователе

Этот эндпоинт возвращает детальную информацию о пользователе по его `chat_id`.

**Запрос:**

```bash
curl -X GET "http://localhost:8000/users/123456789" \
-H "api-key: your_very_strong_and_secret_internal_api_key"
```

**Ответ (успешный):**

```json
{
  "chat_id": 123456789,
  "username": "newuser",
  "ozhivashki": 0,
  "generation_count": 1,
  "last_generation_time": "2024-03-15T12:05:00.000000",
  "registered_at": "2024-03-15T12:00:00.000000",
  "referral_code": "ref_123456789",
  "referred_by": 987654321,
  "referral_bonus_claimed": true,
  "first_generation_time": "2024-03-15T12:05:00.000000",
  "daily_bonus_claimed_today": false,
  "daily_bonus_streak": 0,
  "discount_offered": false,
  "last_activity_time": "2024-03-15T12:05:00.000000",
  "advertising_source": "src_ads_campaign_01",
  "yookassa_payments": {}
}
```

### 4. Создание платежа для пользователя

Этот эндпоинт инициирует создание платежа через YooKassa для указанного пользователя и товара.

**Запрос:**

```bash
curl -X POST "http://localhost:8000/users/123456789/create_payment" \
-H "Content-Type: application/json" \
-H "api-key: your_very_strong_and_secret_internal_api_key" \
-d '{
  "item_name": "Пакет '10 Оживашек'",
  "quantity": 1,
  "price": 100.00
}'
```

**Ответ (успешное создание):**

*Примечание: `payment_url` будет вести на страницу оплаты YooKassa.*

```json
{
  "payment_url": "https://yoomoney.ru/checkout/payments/v2/contract?orderId=2d9977c5-000f-5000-8000-1a3b41f8f216",
  "payment_id": "2d9977c5-000f-5000-8000-1a3b41f8f216"
}
```