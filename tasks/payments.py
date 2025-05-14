import asyncio
import uuid

import httpx
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from yookassa import Configuration as YooKassaConfig
from yookassa import Payment as YooKassaPayment
from yookassa.domain.exceptions import NotFoundError as YooKassaNotFoundError

from .bots import send_user_notification, send_admin_notification
from .config import (YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, API_URL, API_KEY, EMOJI_PARTY, EMOJI_SAD, EMOJI_CHECK,
                     EMOJI_CROSS, EMOJI_WARNING, EMOJI_MAGIC_WAND, pluralize_ozhivashki, logger)
from .database import get_users_collection

YooKassaConfig.account_id = YOOKASSA_SHOP_ID
YooKassaConfig.secret_key = YOOKASSA_SECRET_KEY


async def add_ozhivashki_via_api(chat_id: int, amount: int) -> bool:
    if amount <= 0: return False
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.post(f"{API_URL}/users/{chat_id}/add_ozhivashki/{amount}",
                headers={"api-key": API_KEY})
            response.raise_for_status()
            logger.info(f"Successfully called API to add {amount} ozhivashki for {chat_id}")
            return True
        except httpx.RequestError as e:
            logger.error(f"Network error calling add_ozhivashki API for {chat_id}: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"API error calling add_ozhivashki for {chat_id}: Status {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error calling add_ozhivashki API for {chat_id}: {e}")
        return False


async def check_payment_status_loop():
    users_collection = await get_users_collection()
    if users_collection is None:
        logger.critical("DB collection is None in payment loop")
        return

    logger.info("Payment check task started")

    while True:
        processed_in_iteration = set()
        try:
            users_cursor = users_collection.find({"yookassa_payments": {"$exists": True, "$ne": None, "$ne": {}}})

            async for user in users_cursor:
                chat_id = user.get("chat_id")
                payments = user.get("yookassa_payments", {})

                if not chat_id or not isinstance(payments, dict):
                    logger.warning(f"Skipping user with invalid data: {user.get('_id')}")
                    continue

                payment_ids_to_check = list(payments.keys())

                for payment_id in payment_ids_to_check:
                    if payment_id in processed_in_iteration:
                        continue

                    payment_info = payments.get(payment_id)

                    if not isinstance(payment_info, dict) or "status" not in payment_info:
                        logger.warning(f"Invalid payment_info structure for {payment_id}, user {chat_id}")
                        processed_in_iteration.add(payment_id)
                        continue

                    db_status = payment_info.get("status")
                    already_processed_success = payment_info.get("generations_added", False)

                    if db_status in ["succeeded", "canceled"] and already_processed_success:
                        continue
                    if db_status == "canceled":
                        continue

                    try:
                        logger.debug(f"Checking YooKassa status for payment {payment_id}, user {chat_id}")
                        payment_yookassa = YooKassaPayment.find_one(payment_id)
                        current_yookassa_status = payment_yookassa.status
                        logger.debug(f"YooKassa status for {payment_id} is {current_yookassa_status}")

                    except YooKassaNotFoundError:
                        logger.warning(f"Payment {payment_id} (user {chat_id}) not found in YooKassa")
                        await users_collection.update_one({"chat_id": chat_id}, {
                            "$set": {f"yookassa_payments.{payment_id}.status": "canceled",
                                f"yookassa_payments.{payment_id}.cancellation_details": {
                                    "reason": "not_found_in_yookassa"}}})
                        processed_in_iteration.add(payment_id)
                        continue
                    except Exception as e:
                        logger.error(f"Error querying YooKassa for {payment_id}, user {chat_id}: {e}")
                        continue

                    if current_yookassa_status != db_status:
                        logger.info(
                            f"Status change for {payment_id}, user {chat_id}: {db_status} -> {current_yookassa_status}")
                        update_payload = {"$set": {f"yookassa_payments.{payment_id}.status": current_yookassa_status}}
                        notify_user = False
                        notify_admin = False
                        user_message = ""
                        admin_message = ""
                        ozhivashki_to_add = 0
                        user_markup = None
                        item_name = payment_info.get("item_name", "покупка")

                        if current_yookassa_status == "succeeded" and not already_processed_success:
                            ozhivashki_to_add = payment_info.get("quantity", 0)

                            if ozhivashki_to_add > 0:
                                if await add_ozhivashki_via_api(chat_id, ozhivashki_to_add):
                                    update_payload["$set"][f"yookassa_payments.{payment_id}.generations_added"] = True
                                    logger.info(
                                        f"Successfully added {ozhivashki_to_add} ozhivashki for {chat_id}, payment {payment_id}")

                                    notify_user = True
                                    user_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
                                        text=f"{EMOJI_MAGIC_WAND} Оживить еще!", callback_data="generate_drawing")]])
                                    user_message = f"{EMOJI_PARTY} Оплата прошла успешно! Начислено <b>{ozhivashki_to_add} {pluralize_ozhivashki(ozhivashki_to_add)}</b> ({item_name})."

                                    notify_admin = True
                                    admin_message = f"{EMOJI_CHECK} Успешный платеж {payment_id} ({item_name}) для user {chat_id}. Начислено: {ozhivashki_to_add}."
                                else:
                                    logger.error(
                                        f"Failed to add ozhivashki via API for successful payment {payment_id}, user {chat_id}")
                                    notify_admin = True
                                    admin_message = f"{EMOJI_WARNING} ОШИБКА API начисления для УСПЕШНОГО платежа {payment_id}, user {chat_id}. {ozhivashki_to_add} НЕ начислены."
                                    ozhivashki_to_add = 0
                            else:
                                logger.error(
                                    f"Invalid quantity ({ozhivashki_to_add}) for successful payment {payment_id}, user {chat_id}")
                                update_payload["$set"][f"yookassa_payments.{payment_id}.generations_added"] = True
                                notify_admin = True
                                admin_message = f"{EMOJI_WARNING} ОШИБКА: Некорректное кол-во ({ozhivashki_to_add}) для УСПЕШНОГО платежа {payment_id}, user {chat_id}."

                        elif current_yookassa_status == "canceled":
                            reason = payment_yookassa.cancellation_details.reason if payment_yookassa.cancellation_details else "N/A"
                            party = payment_yookassa.cancellation_details.party if payment_yookassa.cancellation_details else "N/A"
                            logger.info(
                                f"Payment {payment_id} canceled for user {chat_id}. Reason: {reason}, Party: {party}")
                            update_payload["$set"][f"yookassa_payments.{payment_id}.cancellation_details"] = {
                                "reason": reason, "party": party}
                            update_payload["$set"][f"yookassa_payments.{payment_id}.generations_added"] = True

                            notify_user = True
                            user_message = f"{EMOJI_SAD} Платеж ({item_name}) был отменен. Попробуй еще раз или напиши в поддержку, если это ошибка."
                            notify_admin = True
                            admin_message = f"{EMOJI_CROSS} Платеж {payment_id} отменен для user {chat_id}. Причина: {reason} ({party})."

                        else:
                            logger.info(
                                f"Status for {payment_id} updated to {current_yookassa_status} for user {chat_id}")

                        try:
                            await users_collection.update_one({"chat_id": chat_id}, update_payload)
                            processed_in_iteration.add(payment_id)
                        except Exception as db_e:
                            logger.error(f"Failed to update DB for payment {payment_id}, user {chat_id}: {db_e}")
                            notify_user = False
                            notify_admin = False

                        if notify_user:
                            await send_user_notification(chat_id, user_message, reply_markup=user_markup)
                        if notify_admin:
                            await send_admin_notification(admin_message)

                    elif current_yookassa_status == "waiting_for_capture" and db_status != "succeeded":
                        logger.info(f"Payment {payment_id} (user {chat_id}) is waiting_for_capture")
                        try:
                            capture_idempotence_key = str(uuid.uuid4())
                            capture_response = YooKassaPayment.capture(payment_id, {"amount": payment_yookassa.amount},
                                capture_idempotence_key)
                            logger.info(f"Capture result for {payment_id}: status {capture_response.status}")
                            await users_collection.update_one({"chat_id": chat_id},
                                {"$set": {f"yookassa_payments.{payment_id}.status": capture_response.status}})
                            processed_in_iteration.add(payment_id)
                            if capture_response.status == "succeeded":
                                await send_admin_notification(
                                    f"ℹ️ Платеж {payment_id} (user {chat_id}) успешно подтвержден")

                        except Exception as cap_e:
                            logger.error(f"Error capturing payment {payment_id} for user {chat_id}: {cap_e}")

        except Exception as loop_e:
            logger.error(f"Critical error in payment check loop: {loop_e}")
            await asyncio.sleep(60)

        await asyncio.sleep(10)
