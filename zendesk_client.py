# zendesk_client.py

import aiohttp
import logging
import os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio

logger = logging.getLogger(__name__)

# === Получаем настройки из переменных окружения ===
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN")
ZENDESK_GROUP_ID_RAW = os.getenv("ZENDESK_GROUP_ID")
TAGS = (os.getenv("ZENDESK_TAGS") or "from_telegram,auto_created").split(",")

# Проверка обязательных параметров
if not all([ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN]):
    raise ValueError("❌ Missing required Zendesk environment variables: "
                     "ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN")

# Преобразуем group_id в int или None
ZENDESK_GROUP_ID = None
if ZENDESK_GROUP_ID_RAW:
    try:
        ZENDESK_GROUP_ID = int(ZENDESK_GROUP_ID_RAW)
    except ValueError:
        logger.warning(f"Invalid ZENDESK_GROUP_ID: {ZENDESK_GROUP_ID_RAW}. Ignoring.")

BASE_URL = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2"
TIMEOUT_SECONDS = 15

# Ограничение: не более 2 одновременных запросов к Zendesk
zendesk_semaphore = asyncio.Semaphore(2)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    reraise=True
)
async def _make_zendesk_request(method, url, **kwargs):
    """Внутренняя функция с retry и семафором"""
    auth = aiohttp.BasicAuth(f"{ZENDESK_EMAIL}/token", ZENDESK_API_TOKEN)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    async with zendesk_semaphore:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, auth=auth, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = min(int(resp.headers.get("Retry-After", 5)), 30)
                    logger.warning(f"Zendesk 429 — waiting {retry_after} sec")
                    await asyncio.sleep(retry_after)
                    raise aiohttp.ClientResponseError(
                        request_info=resp.request_info,
                        history=resp.history,
                        status=429,
                        message="Too Many Requests"
                    )
                if resp.status >= 400:
                    error_text = await resp.text()
                    logger.error(f"Zendesk error {resp.status}: {error_text}")
                    resp.raise_for_status()
                return await resp.json()


async def create_ticket(subject: str, description: str, requester_name: str, telegram_user_id: int):
    requester_email = f"telegram-{telegram_user_id}@yourcompany.fake"

    ticket_data = {
        "ticket": {
            "subject": subject,
            "comment": {"body": description},
            "requester": {
                "name": requester_name,
                "email": requester_email
            },
            "tags": TAGS
        }
    }
    if ZENDESK_GROUP_ID is not None:
        ticket_data["ticket"]["group_id"] = ZENDESK_GROUP_ID

    try:
        data = await _make_zendesk_request("POST", f"{BASE_URL}/tickets.json", json=ticket_data)
        ticket_id = data["ticket"]["id"]
        ticket_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket_id}"
        return ticket_url, ticket_id
    except Exception as e:
        logger.exception(f"Ошибка создания тикета: {e}")
        return None, None


async def get_ticket_info(ticket_id: int):
    try:
        return await _make_zendesk_request("GET", f"{BASE_URL}/tickets/{ticket_id}.json")
    except Exception as e:
        logger.exception(f"Ошибка получения info тикета {ticket_id}: {e}")
        return None


async def get_ticket_comments(ticket_id: int):
    try:
        data = await _make_zendesk_request("GET", f"{BASE_URL}/tickets/{ticket_id}/comments.json")
        return data.get("comments", [])
    except Exception as e:
        logger.exception(f"Ошибка получения комментариев тикета {ticket_id}: {e}")
        return None