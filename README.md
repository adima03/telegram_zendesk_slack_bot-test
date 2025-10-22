 Deployment 
 Локальный запуск с Docker

1. Склонируйте репозиторий:
   ```bash
   git clone <your-repo-url>
   cd telegram_zendesk_slack_bot
   
2. Создайте и заполните .env:
    bash
    cp .env.example .env
    nano .env  # ← вставьте свои токены

3. Запустите бота:
    docker-compose up --build

4. Остановка:
    docker-compose down

Переменные окружения
переменная:              пример:
TELEGRAM_BOT_TOKEN       123456:ABC...
BOT_USERNAME             my_support_bot
ZENDESK_SUBDOMAIN        mycompany
ZENDESK_EMAIL            admin@mycompany.com/token
ZENDESK_API_TOKEN        kL9pQ2rT5vX8zA3bC6dE7fG0hJ1iK4mN
SLACK_WEBHOOK_URL        https://hooks.slack.com/...
ZENDESK_GROUP_ID         12345678 (не обязательная штука)


## ▶️ 8. Как запустить

### Локально:
```bash
# 1. Создайте .env
cp .env.example .env
nano .env  # ← заполните токенами
# 2. Запустите
docker-compose up --build

В production (VPS):
# На сервере:
git clone <your-repo>
cd telegram_zendesk_slack_bot
cp .env.example .env
nano .env  # ← вставьте production-токены
docker-compose up -d  # запуск в фоне

Проверка работоспособности
После запуска вы должны увидеть в логах: INFO - 🚀 Бот запущен. Ожидание упоминаний...

