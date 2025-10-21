# bot.py

import logging
import time
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from zendesk_client import create_ticket, get_ticket_comments, get_ticket_info
from slack_client import send_slack_notification
import asyncio
import os

# === Настройки безопасности ===
MAX_MESSAGE_LENGTH = 1000  # Макс. 1000 символов в сообщении
RATE_LIMIT_WINDOW = 20     # секунд между запросами от одного пользователя

# Rate limiting: user_id -> timestamp последнего запроса
user_last_request = defaultdict(float)

# Словарь: ключевые слова → тема тикета
TRIGGER_KEYWORDS = {
    "deposit": ["deposit", "депозит", "внести", "пополнить", "top up", "fund"],
    "withdrawal": ["withdraw", "вывод", "снять", "вывести", "cash out", "withdrawal"],
    "login": ["login", "логин", "войти", "авторизация", "не могу зайти", "пароль"],
    "bug": ["bug", "ошибка", "сломалось", "не работает", "crash", "падает"],
    "other": ["help", "помощь", "support", "поддержка", "вопрос"],
}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания активных мониторингов тикетов
active_monitors = {}

# Импортируем конфигурацию
from config import TELEGRAM_BOT_TOKEN, BOT_USERNAME


def detect_ticket_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in TRIGGER_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category.capitalize()
    return "Other"


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    raw_text = message.text or ""
    chat_id = message.chat.id

    # === 1. Rate limiting по user_id ===
    now = time.time()
    if now - user_last_request[user.id] < RATE_LIMIT_WINDOW:
        await message.reply_text("⏳ Please wait before sending another request.")
        return
    user_last_request[user.id] = now

    # === 2. Ограничение длины сообщения ===
    if len(raw_text) > MAX_MESSAGE_LENGTH:
        await message.reply_text(f"❌ Message is too long. Maximum allowed: {MAX_MESSAGE_LENGTH} characters.")
        return

    # === Распознавание упоминания ===
    mentioned = False
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mentioned_username = raw_text[entity.offset + 1 : entity.offset + entity.length]
                if mentioned_username == BOT_USERNAME:
                    mentioned = True
                    break

    if not mentioned:
        # Логируем ТОЛЬКО метаданные, НЕ текст!
        logger.debug(f"Упоминание не обнаружено от user_id={user.id} в chat_id={chat_id}")
        return

    # === Безопасное логирование: НЕТ тела сообщения! ===
    logger.info(f"✅ Упоминание от user_id={user.id}, username={user.username}, chat_id={chat_id}")

    # === Очистка текста от упоминания бота ===
    clean_text = raw_text
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mentioned_username = raw_text[entity.offset + 1 : entity.offset + entity.length]
                if mentioned_username == BOT_USERNAME:
                    mentioned_full = raw_text[entity.offset : entity.offset + entity.length]
                    clean_text = clean_text.replace(mentioned_full, "", 1).strip()

    # === Формируем информацию о чате ===
    chat = message.chat
    if chat.type == "private":
        chat_info = f"Private chat with {user.full_name or 'User'}"
    elif chat.title:
        chat_info = f"Group: {chat.title}"
        if chat.username:
            chat_info += f" (@{chat.username})"
    else:
        chat_info = f"Chat ID: {chat.id}"

    # === Определяем категорию ===
    category = detect_ticket_category(clean_text)
    subject = f"[Telegram] {category}"

    # === Формируем описание ===
    description = (
        f"Message: {clean_text}\n"
        f"From: {user.full_name or '—'} (@{user.username or 'unknown'})\n"
        f"{chat_info}"
    )

    # === Создаём тикет ===
    ticket_url, ticket_id = await create_ticket(
        subject=subject,
        description=description,
        requester_name=user.full_name or "Telegram User",
        telegram_user_id=user.id
    )

    if not ticket_url:
        await message.reply_text("❌ Failed to create a support ticket. Please try again later.")
        return

    # === Отправляем в Slack ===
    slack_msg = (
        f"🆕 New request from Telegram\n\n"
        f"📌 *Category:* {category}\n"
        f"💬 *Message:* {clean_text[:250]}{'...' if len(clean_text) > 250 else ''}\n"
        f"👤 *User:* {user.full_name or '—'} (<https://t.me/{user.username}|@{user.username}>)\n"
        f"🏢 *Chat:* {chat.title if chat.title else 'Private chat'}\n"
        f"🔗 *Ticket:* <{ticket_url}|Open in Zendesk>"
    )
    await send_slack_notification(slack_msg)

    # === Отвечаем пользователю ===
    await message.reply_text(f"✅ Support ticket #{ticket_id} has been created.")

    # === ЗАЩИТА ОТ ДУБЛИРОВАНИЯ МОНИТОРИНГА ===
    if ticket_id in active_monitors:
        logger.warning(f"Мониторинг для тикета {ticket_id} уже запущен")
    else:
        task = asyncio.create_task(
            monitor_ticket_comments(
                ticket_id=ticket_id,
                user_id=user.id,
                chat_id=chat_id,
                original_message_id=message.message_id,
                bot=context.bot
            )
        )
        active_monitors[ticket_id] = task
        task.add_done_callback(lambda t: active_monitors.pop(ticket_id, None))


async def monitor_ticket_comments(ticket_id: int, user_id: int, chat_id: int, original_message_id: int, bot):
    logger.info(f"🚀 Мониторинг тикета {ticket_id} запущен")
    last_comment_id = None

    while True:
        try:
            comments = await get_ticket_comments(ticket_id)
            if not comments:
                await asyncio.sleep(15)
                continue

            latest = comments[-1]
            comment_id = latest["id"]
            author_id = latest.get("author_id")

            ticket_info = await get_ticket_info(ticket_id)
            requester_id = ticket_info["ticket"]["requester_id"]

            if author_id == requester_id:
                last_comment_id = comment_id
                await asyncio.sleep(15)
                continue

            if comment_id != last_comment_id:
                body = latest["body"]
                if "—\nSent from" in body:
                    body = body.split("—\nSent from")[0].strip()

                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"💬 *Support reply:*\n{body}",
                        reply_to_message_id=original_message_id,
                        parse_mode="Markdown"
                    )
                    last_comment_id = comment_id
                except Exception as e:
                    logger.error(f"Ошибка отправки в Telegram: {e}")

        except Exception as e:
            logger.error(f"Ошибка мониторинга тикета {ticket_id}: {e}")

        await asyncio.sleep(15)


def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_mention))
    logger.info("🚀 Бот запущен. Ожидание упоминаний...")
    application.run_polling()


if __name__ == "__main__":
    main()