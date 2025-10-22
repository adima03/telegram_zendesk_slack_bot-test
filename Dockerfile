# Используем официальный Python-образ
FROM python:3.9-slim

# Устанавливаем зависимости системы (для некоторых пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаём директорию для сохранения состояния (если используется файл)
RUN mkdir -p /data

# Запускаем бота
CMD ["python", "bot.py"]