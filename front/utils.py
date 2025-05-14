from typing import Optional

import httpx
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup

from .config import (bot, logger, API_URL, API_KEY, CURRENCY_NAME, CURRENCY_NAME_PLURAL_2_4, CURRENCY_NAME_PLURAL_5_0)


def pluralize_ozhivashki(count: int) -> str:
    if 11 <= count % 100 <= 19:
        return CURRENCY_NAME_PLURAL_5_0
    last_digit = count % 10
    if last_digit == 1:
        return CURRENCY_NAME
    elif 2 <= last_digit <= 4:
        return CURRENCY_NAME_PLURAL_2_4
    else:
        return CURRENCY_NAME_PLURAL_5_0


async def safe_delete_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Message {message_id} deleted for chat {chat_id}")
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e) or "message can't be deleted" in str(e):
            logger.debug(f"Message {message_id} already deleted or cannot be deleted.")
        else:
            logger.warning(f"Error deleting message {message_id} for chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting message {message_id} for chat {chat_id}: {e}")


async def send_or_edit_message(chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None,
                               state: Optional[FSMContext] = None, edit_message_id: Optional[int] = None) -> Optional[
    int]:
    new_message_id = None
    if edit_message_id:
        try:
            await bot.edit_message_text(text=text, chat_id=chat_id, message_id=edit_message_id,
                                        reply_markup=reply_markup)
            logger.debug(f"Message {edit_message_id} edited for chat {chat_id}")
            new_message_id = edit_message_id
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                logger.debug(f"Message {edit_message_id} not modified.")
                new_message_id = edit_message_id
            else:
                logger.warning(f"Failed to edit message {edit_message_id}: {e}. Sending new.")
    if new_message_id is None:
        try:
            sent_message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            logger.debug(f"New message {sent_message.message_id} sent for chat {chat_id}")
            new_message_id = sent_message.message_id
        except Exception as e:
            logger.error(f"Failed to send message for chat {chat_id}: {e}")
            return None

    if state and new_message_id:
        await state.update_data(last_bot_message_id=new_message_id)
    return new_message_id


async def get_user_data(chat_id: int) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(f"{API_URL}/users/{chat_id}", headers={"api-key": API_KEY})
            if response.status_code == 404:
                logger.info(f"User {chat_id} not found in API.")
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error getting user {chat_id}: Status {e.response.status_code}, Resp: {e.response.text[:100]}")
        except httpx.RequestError as e:
            logger.error(f"Network error getting user {chat_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting user {chat_id}: {e}")
        return None


async def create_user(chat_id: int, username: Optional[str], referral_code: Optional[str] = None,
                      source_code: Optional[str] = None) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"chat_id": chat_id, "username": username or f"user_{chat_id}", }
        if referral_code:
            payload["referral_code"] = referral_code
        if source_code:
            payload["advertising_source"] = source_code
        try:
            response = await client.post(f"{API_URL}/users", json=payload, headers={"api-key": API_KEY})
            response.raise_for_status()
            logger.info(f"Пользователь {chat_id} создан успешно.")
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка создания пользователя {chat_id}: {e}")
            return None
