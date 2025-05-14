import asyncio
import base64
import uuid
from datetime import datetime
from io import BytesIO
from typing import List

from PIL import Image
from fastapi import HTTPException, Header
from google import genai
from google.genai import types as genai_types
from yookassa import Payment as YooKassaPayment

from .config import (GEMINI_API_KEYS, NUM_KEYS, REQUESTS_PER_MINUTE_LIMIT, REQUESTS_PER_DAY_LIMIT, GENERATION_PROMPT,
                     API_KEY, logger, TELEGRAM_BOT_USERNAME)
from .db import redis_client, users_collection, get_db_user
from .models import GenerationResponse, PaymentInfo


async def get_api_key_dependency(
        internal_api_key: str = Header(..., alias="api_key", description="Внутренний API ключ")):
    if internal_api_key != API_KEY:
        logger.warning(f"Попытка доступа с неверным API ключом: {internal_api_key}")
        raise HTTPException(status_code=401, detail="Неверный API ключ")
    return internal_api_key


async def reset_daily_quota(key_index: int):
    if not redis_client:
        logger.error("Сервис Redis недоступен, не могу сбросить дневную квоту.")
        return
    key_prefix = f"gemini_key:{key_index}"
    try:
        await redis_client.set(f"{key_prefix}:daily_requests", REQUESTS_PER_DAY_LIMIT)
        await redis_client.set(f"{key_prefix}:last_daily_reset", datetime.now().timestamp())
        logger.info(f"Дневной лимит для ключа {key_index} сброшен.")
    except Exception as e:
        logger.error(f"Не удалось сбросить дневную квоту для ключа {key_index}: {e}")


async def get_available_key() -> int:
    if not redis_client:
        logger.error("Клиент Redis не инициализирован. Невозможно получить API-ключ.")
        raise HTTPException(status_code=503, detail="Сервис временно недоступен (Redis)")

    while True:
        available_keys_quota = []
        current_time = datetime.now()
        for i in range(NUM_KEYS):
            key_prefix = f"gemini_key:{i}"
            try:
                last_daily_reset_ts_bytes = await redis_client.get(f"{key_prefix}:last_daily_reset")
                if last_daily_reset_ts_bytes:
                    last_daily_reset_ts = float(last_daily_reset_ts_bytes)
                    last_daily_reset_time = datetime.fromtimestamp(last_daily_reset_ts)
                    if current_time.day != last_daily_reset_time.day:
                        await reset_daily_quota(i)
                else:
                    await reset_daily_quota(i)

                minute_requests_bytes = await redis_client.get(f"{key_prefix}:minute_requests")
                daily_requests_bytes = await redis_client.get(f"{key_prefix}:daily_requests")

                minute_requests_remaining = int(
                    minute_requests_bytes) if minute_requests_bytes else REQUESTS_PER_MINUTE_LIMIT
                daily_requests_remaining = int(daily_requests_bytes) if daily_requests_bytes else REQUESTS_PER_DAY_LIMIT

                if minute_requests_remaining > 0 and daily_requests_remaining > 0:
                    available_keys_quota.append({'index': i, 'daily_quota': daily_requests_remaining})

            except ConnectionError as e:
                logger.error(f"Ошибка подключения Redis при проверке ключа {i}: {e}")
                raise HTTPException(status_code=503, detail="Сервис временно недоступен (Redis)")
            except Exception as e:
                logger.error(f"Ошибка проверки квоты для ключа {i}: {e}")

        if available_keys_quota:
            best_key = max(available_keys_quota, key=lambda k: k['daily_quota'])
            logger.info(f"Выбран индекс ключа Gemini {best_key['index']} с дневной квотой: {best_key['daily_quota']}")
            return best_key['index']
        else:
            logger.info("Нет доступных ключей Gemini в соответствии с квотой, ожидание...")
            await asyncio.sleep(0.2)


async def decrement_quota(key_index: int):
    if not redis_client:
        logger.error("Клиент Redis не инициализирован. Невозможно уменьшить квоту.")
        return

    key_prefix = f"gemini_key:{key_index}"
    try:
        minute_requests_remaining = await redis_client.decr(f"{key_prefix}:minute_requests")
        if minute_requests_remaining < 0:
            await redis_client.set(f"{key_prefix}:minute_requests", 0)

        daily_requests_remaining = await redis_client.decr(f"{key_prefix}:daily_requests")
        if daily_requests_remaining < 0:
            await redis_client.set(f"{key_prefix}:daily_requests", 0)

        logger.info(f"Уменьшена квота для ключа {key_index}. "
                    f"Осталось в минуту: {max(0, minute_requests_remaining if minute_requests_remaining is not None else 0)}, "
                    f"Осталось в день: {max(0, daily_requests_remaining if daily_requests_remaining is not None else 0)}")
    except ConnectionError as e:
        logger.error(f"Ошибка подключения Redis при уменьшении квоты для ключа {key_index}: {e}")
    except Exception as e:
        logger.error(f"Не удалось уменьшить квоту для ключа {key_index}: {e}")


async def _apply_referral_bonus(chat_id: int, referrer_id: int):
    if not users_collection:
        logger.error("Коллекция пользователей не инициализирована, не могу применить реферальный бонус.")
        return
    referrer_user = await get_db_user(referrer_id)
    if referrer_user:
        referrer_update_result = await users_collection.update_one({"chat_id": referrer_id},
            {"$inc": {"ozhivashki": 2}})
        if referrer_update_result.modified_count > 0:
            await users_collection.update_one({"chat_id": chat_id}, {"$set": {"referral_bonus_claimed": True}})
            logger.info(
                f"Начислено 2 реферальных оживашки пригласившему {referrer_id} за первую генерацию пользователя {chat_id}.")
        else:
            logger.warning(f"Не удалось обновить баланс оживашек пригласившего {referrer_id}.")
    else:
        logger.warning(f"Пригласивший {referrer_id} не найден для пользователя {chat_id}.")


async def generate_images_service(chat_id: int, image_bytes: bytes) -> GenerationResponse:
    if not users_collection:
        logger.error("Коллекция пользователей не инициализирована.")
        raise HTTPException(status_code=500, detail="Ошибка сервера: база данных пользователей недоступна.")

    user = await get_db_user(chat_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    current_ozhivashki = user.get("ozhivashki", 0)
    if current_ozhivashki <= 0:
        logger.warning(f"Пользователь {chat_id} попытался сгенерировать изображение с 0 оживашек.")
        raise HTTPException(status_code=402, detail="Недостаточно оживашек")

    ozhivashki_spent = 1
    new_balance = current_ozhivashki - ozhivashki_spent
    generation_count = user.get("generation_count", 0) + 1
    streak_bonus_ozhivashka = 1 if generation_count % 5 == 0 else 0
    new_balance += streak_bonus_ozhivashka

    update_fields = {"$inc": {"ozhivashki": -ozhivashki_spent + streak_bonus_ozhivashka, "generation_count": 1},
        "$set": {"last_generation_time": datetime.now(), "last_activity_time": datetime.now()}}
    if user.get("generation_count", 0) == 0:
        update_fields["$set"]["first_generation_time"] = datetime.now()

    await users_collection.update_one({"chat_id": chat_id}, update_fields)
    logger.info(
        f"Пользователь {chat_id}: Потрачено {ozhivashki_spent} оживашка, новое количество генераций {generation_count}. Бонус за серию: {streak_bonus_ozhivashka}. Новый баланс: {new_balance}")

    referrer_id = user.get("referred_by")
    is_first_generation = generation_count == 1
    referral_bonus_claimed = user.get("referral_bonus_claimed", False)

    if is_first_generation and referrer_id and not referral_bonus_claimed:
        await _apply_referral_bonus(chat_id, referrer_id)

    try:
        image_pil = Image.open(BytesIO(image_bytes))
        if image_pil.mode == 'RGBA':
            image_pil = image_pil.convert('RGB')
        logger.info(
            f"Изображение загружено для пользователя {chat_id}. Размер: {image_pil.size}, Режим: {image_pil.mode}")

        needs_bonus = (generation_count == 1) or (generation_count % 2 == 0)
        num_main_images = 4
        num_bonus_images = 2 if needs_bonus else 0
        total_images_to_generate = num_main_images + num_bonus_images

        logger.info(
            f"Запрос {total_images_to_generate} изображений ({num_main_images} основных + {num_bonus_images} бонусных) для пользователя {chat_id} (Генерация #{generation_count}).")

        main_images_b64: List[str] = []
        bonus_images_b64: List[str] = []
        generated_count = 0

        for i in range(total_images_to_generate):
            if not GEMINI_API_KEYS:
                logger.error("Отсутствуют API ключи Gemini.")
                raise HTTPException(status_code=503, detail="Сервис генерации временно недоступен (нет ключей)")

            selected_key_index = await get_available_key()
            api_key_to_use = GEMINI_API_KEYS[selected_key_index]

            genai.configure(api_key=api_key_to_use)
            model = genai.GenerativeModel("gemini-1.5-flash-latest")

            logger.info(
                f"Выполнение вызова Gemini #{i + 1}/{total_images_to_generate} с использованием ключа с индексом {selected_key_index} для пользователя {chat_id}")

            generation_config = genai_types.GenerationConfig(temperature=0.6, candidate_count=1)

            response = await model.generate_content_async(contents=[GENERATION_PROMPT, image_pil],
                generation_config=generation_config)
            await decrement_quota(selected_key_index)

            image_found = False
            if response.candidates:
                candidate = response.candidates[0]
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    block_reason = response.prompt_feedback.block_reason.name
                    block_msg = response.prompt_feedback.block_reason_message
                    logger.error(f"Генерация заблокирована для вызова #{i + 1}. Причина: {block_reason} - {block_msg}")
                    raise HTTPException(status_code=400,
                                        detail=f"Генерация заблокирована: {block_reason} - {block_msg}")

                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                            img_bytes = part.inline_data.data
                            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                            if len(main_images_b64) < num_main_images:
                                main_images_b64.append(img_b64)
                            else:
                                bonus_images_b64.append(img_b64)
                            generated_count += 1
                            image_found = True
                            logger.info(f"Успешно обработано изображение из вызова #{i + 1} для пользователя {chat_id}")
                            break
            if not image_found:
                logger.warning(
                    f"Не удалось извлечь изображение из ответа Gemini для вызова #{i + 1}, пользователь {chat_id}.")

        if generated_count < num_main_images:
            logger.error(
                f"Не удалось сгенерировать достаточно основных изображений для пользователя {chat_id}. Получено {generated_count}/{num_main_images}.")
            raise Exception("ИИ не смог сгенерировать необходимое количество основных изображений.")

        logger.info(
            f"Успешно сгенерированы изображения для {chat_id}. Основные: {len(main_images_b64)}, Бонусные: {len(bonus_images_b64)}")
        return GenerationResponse(main_images=main_images_b64, bonus_images=bonus_images_b64,
                                  ozhivashki_spent=ozhivashki_spent, new_balance=new_balance)

    except HTTPException as http_exc:
        logger.error(f"HTTP ошибка при генерации для {chat_id}: {http_exc.detail}")
        await users_collection.update_one({"chat_id": chat_id},
                                          {"$inc": {"ozhivashki": ozhivashki_spent, "generation_count": -1}})
        logger.info(f"Возвращена {ozhivashki_spent} оживашка и уменьшен счетчик генераций для {chat_id} из-за ошибки.")
        raise http_exc  # Re-raise the HTTPException
    except Exception as e:
        logger.error(f"Ошибка в процессе генерации для {chat_id}: {e}", exc_info=True)
        await users_collection.update_one({"chat_id": chat_id},
                                          {"$inc": {"ozhivashki": ozhivashki_spent, "generation_count": -1}})
        logger.info(
            f"Возвращена {ozhivashki_spent} оживашка и уменьшен счетчик генераций для {chat_id} из-за непредвиденной ошибки.")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при генерации изображений.")


async def create_yookassa_payment_service(chat_id: int, item_name: str, quantity: int, price: float) -> dict:
    if not users_collection:
        logger.error("Коллекция пользователей не инициализирована.")
        raise HTTPException(status_code=500, detail="Ошибка сервера: база данных пользователей недоступна.")
    if not TELEGRAM_BOT_USERNAME:
        logger.error("TELEGRAM_BOT_USERNAME не настроен для URL возврата YooKassa.")
        raise HTTPException(status_code=500, detail="Ошибка конфигурации сервера.")

    user = await get_db_user(chat_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    idempotence_key = str(uuid.uuid4())
    try:
        payment_payload = {"amount": {"value": f"{price:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{TELEGRAM_BOT_USERNAME}"},
            "description": f"{item_name} для Оживи Рисунок (user {chat_id})",
            "metadata": {"chat_id": str(chat_id), "quantity": quantity, "item_name": item_name}, "capture": True}
        payment = YooKassaPayment.create(payment_payload, idempotence_key)

    except Exception as e:
        logger.error(f"Ошибка YooKassa Payment.create для chat_id={chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка провайдера платежей")

    payment_id = payment.id
    confirmation_url = payment.confirmation.confirmation_url if payment.confirmation else None

    if not confirmation_url:
        logger.error(f"YooKassa не вернула confirmation_url для платежа {payment_id}, chat_id={chat_id}")
        raise HTTPException(status_code=500, detail="Не удалось получить URL подтверждения платежа")

    payment_info_to_save = PaymentInfo(item_name=item_name, quantity=quantity, price=price, status=payment.status,
        created_at=datetime.now())
    try:
        payment_dict = payment_info_to_save.model_dump(mode='json')
        await users_collection.update_one({"chat_id": chat_id},
            {"$set": {f"yookassa_payments.{payment_id}": payment_dict}})
    except Exception as db_e:
        logger.error(f"Не удалось сохранить информацию о платеже {payment_id} в БД для chat_id={chat_id}: {db_e}",
                     exc_info=True)

    logger.info(f"Платеж {payment_id} создан для chat_id={chat_id}, URL: {confirmation_url}")
    return {"payment_url": confirmation_url, "payment_id": payment_id}
