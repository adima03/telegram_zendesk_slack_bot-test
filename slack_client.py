# slack_client.py

import aiohttp
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio

from config import SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
async def send_slack_notification(message: str):
    if not SLACK_WEBHOOK_URL or "hooks.slack.com" not in SLACK_WEBHOOK_URL:
        logger.warning("Slack webhook не настроен")
        return

    payload = {"text": message, "mrkdwn": True}
    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(SLACK_WEBHOOK_URL, json=payload) as resp:
            response_text = await resp.text()
            if resp.status == 200 and response_text.strip() == "ok":
                logger.info("✅ Slack: сообщение доставлено")
            else:
                logger.error(f"❌ Slack ошибка: {resp.status} — {response_text}")
                resp.raise_for_status()