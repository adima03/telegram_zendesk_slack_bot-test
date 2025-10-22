# state_manager.py
import json
import os
import logging
from typing import Dict, Any

# Путь к файлу состояния (можно переопределить через .env)
STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
logger = logging.getLogger(__name__)


def load_state() -> Dict[int, Any]:
    """Загружает активные мониторинги из JSON-файла."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            # Ключи в JSON — строки, преобразуем обратно в int
            return {int(ticket_id): data for ticket_id, data in raw_data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки состояния из {STATE_FILE}: {e}")
        return {}


def save_state(state: Dict[int, Any]):
    """Сохраняет состояние в JSON-файл."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения состояния в {STATE_FILE}: {e}")


def add_active_monitor(ticket_id: int, user_id: int, chat_id: int, message_id: int):
    """Добавляет тикет в список активных мониторингов."""
    state = load_state()
    state[ticket_id] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id
    }
    save_state(state)


def remove_active_monitor(ticket_id: int):
    """Удаляет тикет из списка активных мониторингов."""
    state = load_state()
    state.pop(ticket_id, None)
    save_state(state)