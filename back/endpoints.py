import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends

from .config import logger, TELEGRAM_BOT_USERNAME, NUM_KEYS
from .db import users_collection, get_db_user, update_last_activity, advertising_sources_collection, redis_client
from .models import User, UserCreate, PaymentRequestBody, GenerationResponse, SourceCreate
from .services import (get_api_key_dependency, generate_images_service, create_yookassa_payment_service)

router = APIRouter()


@router.post("/generate_source_link", dependencies=[Depends(get_api_key_dependency)])
async def generate_source_link_endpoint(source_data: SourceCreate):
    """Создает уникальную ссылку для отслеживания источника привлечения пользователей."""
    if not advertising_sources_collection:
        logger.warning("Запрос ссылки на источник при недоступной коллекции источников")
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен (коллекция источников)")
    if not TELEGRAM_BOT_USERNAME:
        logger.warning("Запрос ссылки на источник при отсутствии имени пользователя Telegram бота")
        raise HTTPException(status_code=500, detail="Имя пользователя Telegram бота не настроено")

    source_code = f"src_{uuid.uuid4().hex[:8]}"
    new_source_doc = {"source_code": source_code, "campaign_name": source_data.campaign_name,
                      "created_at": datetime.now()}
    result = await advertising_sources_collection.insert_one(new_source_doc)
    if not result.inserted_id:
        logger.error(f"Не удалось создать рекламный источник: {source_data.campaign_name}")
        raise HTTPException(status_code=500, detail="Не удалось создать ссылку")

    link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={source_code}"
    logger.info(f"Создана ссылка на источник: код {source_code}, кампания {source_data.campaign_name}")
    return {"source_code": source_code, "link": link}


@router.post("/users", response_model=User, dependencies=[Depends(get_api_key_dependency)])
async def create_user_endpoint(user_data: UserCreate):
    """Создает нового пользователя или возвращает существующего, если он уже зарегистрирован."""
    if not users_collection:
        logger.warning("Запрос создания пользователя при недоступной коллекции пользователей")
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")

    existing_user = await get_db_user(user_data.chat_id)
    if existing_user:
        logger.warning(f"Попытка создать существующего пользователя: {user_data.chat_id}")
        existing_user.pop("_id", None)
        return User(**existing_user)

    now = datetime.now()
    new_user_doc = {"chat_id": user_data.chat_id, "username": user_data.username, "ozhivashki": 1,
                    "generation_count": 0, "last_generation_time": None, "registered_at": now,
                    "referral_code": f"ref_{user_data.chat_id}", "referred_by": None, "referral_bonus_claimed": False,
                    "first_generation_time": None, "daily_bonus_claimed_today": False, "daily_bonus_streak": 0,
                    "discount_offered": False, "last_activity_time": now, "yookassa_payments": {}}

    if user_data.referral_code and user_data.referral_code.startswith("ref_"):
        try:
            referrer_id = int(user_data.referral_code.split("_")[1])
            if referrer_id != user_data.chat_id:
                referrer_exists = await get_db_user(referrer_id)
                if referrer_exists:
                    new_user_doc["referred_by"] = referrer_id
                    logger.info(f"Пользователь {user_data.chat_id} был приглашен {referrer_id}")
                else:
                    logger.warning(
                        f"Пригласивший пользователь {referrer_id} не найден для реферального кода {user_data.referral_code}")
            else:
                logger.warning(
                    f"Пользователь {user_data.chat_id} попытался использовать свой собственный реферальный код: {user_data.referral_code}")
        except (IndexError, ValueError):
            logger.warning(f"Не удалось разобрать реферальный код для {user_data.chat_id}: {user_data.referral_code}")

    if user_data.advertising_source:
        new_user_doc["advertising_source"] = user_data.advertising_source
        logger.info(f"Пользователь {user_data.chat_id} зарегистрирован с источника: {user_data.advertising_source}")

    result = await users_collection.insert_one(new_user_doc)
    if not result.inserted_id:
        logger.error(f"Не удалось добавить нового пользователя {user_data.chat_id} в базу данных")
        raise HTTPException(status_code=500, detail="Не удалось создать пользователя")

    logger.info(f"Пользователь создан: {user_data.chat_id} с 1 оживашкой. Username: {user_data.username}")
    new_user_doc.pop("_id", None)  # Ensure _id is not in the response if it was added by insert_one
    return User(**new_user_doc)


@router.get("/api_key_limits", dependencies=[Depends(get_api_key_dependency)])
async def get_api_key_limits_endpoint():
    """Возвращает текущие лимиты использования для каждого API ключа Gemini."""
    if not redis_client:
        logger.warning("Запрос лимитов API ключей при недоступном Redis.")
        raise HTTPException(status_code=503, detail="Redis недоступен")
    key_limits = []
    for i in range(NUM_KEYS):
        key_prefix = f"gemini_key:{i}"
        try:
            minute_requests_bytes = await redis_client.get(f"{key_prefix}:minute_requests")
            daily_requests_bytes = await redis_client.get(f"{key_prefix}:daily_requests")
            minute_requests_remaining = int(minute_requests_bytes) if minute_requests_bytes else 0
            daily_requests_remaining = int(daily_requests_bytes) if daily_requests_bytes else 0
            key_limits.append({"key_index": i, "minute_requests_remaining": minute_requests_remaining,
                               "daily_requests_remaining": daily_requests_remaining})
        except Exception as e:
            logger.error(f"Ошибка получения лимитов для ключа {i}: {e}")
            key_limits.append({"key_index": i, "error": str(e)})
    return key_limits


@router.get("/stats", dependencies=[Depends(get_api_key_dependency)])
async def get_stats_endpoint():
    """Собирает и возвращает расширенную статистику по пользователям, генерациям и платежам."""
    if not users_collection:
        logger.warning("Запрос статистики при недоступной коллекции пользователей")
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")

    total_users = await users_collection.count_documents({})

    pipeline_generations = [{"$group": {"_id": None, "total_generations": {"$sum": "$generation_count"}}}]
    result_generations = await users_collection.aggregate(pipeline_generations).to_list(None)
    total_generations = result_generations[0]["total_generations"] if result_generations and result_generations[0].get(
        "total_generations") is not None else 0

    pipeline_revenue = [{"$project": {"successful_payments": {
        "$filter": {"input": {"$objectToArray": "$yookassa_payments"}, "as": "payment",
                    "cond": {"$eq": ["$$payment.v.status", "succeeded"]}}}}}, {"$unwind": "$successful_payments"}, {
        "$group": {"_id": None, "total_revenue": {"$sum": "$successful_payments.v.price"},
                   "total_successful_payments": {"$sum": 1}}}]
    result_revenue = await users_collection.aggregate(pipeline_revenue).to_list(None)
    total_revenue = result_revenue[0]["total_revenue"] if result_revenue and result_revenue[0].get(
        "total_revenue") is not None else 0
    total_successful_payments = result_revenue[0]["total_successful_payments"] if result_revenue and result_revenue[
        0].get("total_successful_payments") is not None else 0

    seven_days_ago = datetime.now() - timedelta(days=7)
    active_users = await users_collection.count_documents({"last_generation_time": {"$gte": seven_days_ago}})

    pipeline_time_to_first_gen = [
        {"$match": {"first_generation_time": {"$exists": True}, "registered_at": {"$exists": True}}},
        {"$project": {"time_to_first_gen": {"$subtract": ["$first_generation_time", "$registered_at"]}}},
        {"$group": {"_id": None, "avg_time_to_first_gen": {"$avg": "$time_to_first_gen"}}}]
    result_time_to_first_gen = await users_collection.aggregate(pipeline_time_to_first_gen).to_list(None)
    avg_time_to_first_gen_ms = result_time_to_first_gen[0]["avg_time_to_first_gen"] if result_time_to_first_gen and \
                                                                                       result_time_to_first_gen[0].get(
                                                                                           "avg_time_to_first_gen") is not None else 0
    avg_time_to_first_gen_hours = avg_time_to_first_gen_ms / 3600000 if avg_time_to_first_gen_ms else 0

    users_with_zero_generations = await users_collection.count_documents({"generation_count": 0})
    percentage_zero_generations = (users_with_zero_generations / total_users * 100) if total_users > 0 else 0

    average_payment = total_revenue / total_successful_payments if total_successful_payments > 0 else 0

    pipeline_repeat = [{"$project": {"successful_payments_count": {"$size": {
        "$filter": {"input": {"$objectToArray": "$yookassa_payments"}, "as": "payment",
                    "cond": {"$eq": ["$$payment.v.status", "succeeded"]}}}}}}, {"$group": {"_id": None,
                                                                                           "total_repeat_payments": {
                                                                                               "$sum": {"$cond": [{
                                                                                                   "$gt": [
                                                                                                       "$successful_payments_count",
                                                                                                       1]}, {
                                                                                                   "$subtract": [
                                                                                                       "$successful_payments_count",
                                                                                                       1]}, 0]}}}}]
    result_repeat = await users_collection.aggregate(pipeline_repeat).to_list(None)
    total_repeat_payments = result_repeat[0]["total_repeat_payments"] if result_repeat and result_repeat[0].get(
        "total_repeat_payments") is not None else 0
    percentage_repeat_payments = (
            total_repeat_payments / total_successful_payments * 100) if total_successful_payments > 0 else 0

    pipeline_paying_users = [{"$match": {"yookassa_payments": {"$exists": True}}}, {"$project": {
        "has_successful_payment": {"$gt": [{"$size": {
            "$filter": {"input": {"$objectToArray": "$yookassa_payments"}, "as": "payment",
                        "cond": {"$eq": ["$$payment.v.status", "succeeded"]}}}}, 0]}}},
                             {"$match": {"has_successful_payment": True}}, {"$count": "paying_users"}]
    result_paying_users = await users_collection.aggregate(pipeline_paying_users).to_list(None)
    paying_users = result_paying_users[0]["paying_users"] if result_paying_users and result_paying_users[0].get(
        "paying_users") is not None else 0
    average_payments_per_paying_user = total_successful_payments / paying_users if paying_users > 0 else 0

    pipeline_activity_depth = [{
        "$match": {"first_generation_time": {"$exists": True}, "last_generation_time": {"$exists": True},
                   "generation_count": {"$gte": 2}}},
        {"$project": {"activity_depth": {"$subtract": ["$last_generation_time", "$first_generation_time"]}}},
        {"$group": {"_id": None, "avg_activity_depth": {"$avg": "$activity_depth"}}}]
    result_activity_depth = await users_collection.aggregate(pipeline_activity_depth).to_list(None)
    avg_activity_depth_ms = result_activity_depth[0]["avg_activity_depth"] if result_activity_depth and \
                                                                              result_activity_depth[0].get(
                                                                                  "avg_activity_depth") is not None else 0
    avg_activity_depth_days = avg_activity_depth_ms / 86400000 if avg_activity_depth_ms else 0  # 1000*60*60*24

    threshold = 1000.0
    pipeline_ltv = [{"$project": {"total_revenue_per_user": {"$sum": {"$map": {"input": {
        "$filter": {"input": {"$objectToArray": "$yookassa_payments"}, "as": "payment",
                    "cond": {"$eq": ["$$payment.v.status", "succeeded"]}}}, "as": "payment",
        "in": "$$payment.v.price"}}}}}, {"$match": {"total_revenue_per_user": {"$gt": threshold}}},
        {"$count": "users_with_high_ltv"}]
    result_ltv = await users_collection.aggregate(pipeline_ltv).to_list(None)
    users_with_high_ltv = result_ltv[0]["users_with_high_ltv"] if result_ltv and result_ltv[0].get(
        "users_with_high_ltv") is not None else 0
    percentage_high_ltv = (users_with_high_ltv / total_users * 100) if total_users > 0 else 0

    pipeline_time_between = [{
        "$match": {"first_generation_time": {"$exists": True}, "last_generation_time": {"$exists": True},
                   "generation_count": {"$gte": 2}}}, {"$project": {"time_between": {
        "$divide": [{"$subtract": ["$last_generation_time", "$first_generation_time"]},
                    {"$subtract": ["$generation_count", 1]}]}}},
        {"$group": {"_id": None, "avg_time_between": {"$avg": "$time_between"}}}]
    result_time_between = await users_collection.aggregate(pipeline_time_between).to_list(None)
    avg_time_between_ms = result_time_between[0]["avg_time_between"] if result_time_between and result_time_between[
        0].get("avg_time_between") is not None else 0
    avg_time_between_days = avg_time_between_ms / 86400000 if avg_time_between_ms else 0

    pipeline_failed_payments = [{"$project": {"has_failed_payment": {"$gt": [{"$size": {
        "$filter": {"input": {"$objectToArray": "$yookassa_payments"}, "as": "payment",
                    "cond": {"$in": ["$$payment.v.status", ["failed", "canceled"]]}}}}, 0]}}},
        {"$match": {"has_failed_payment": True}}, {"$count": "users_with_failed_payments"}]
    result_failed_payments = await users_collection.aggregate(pipeline_failed_payments).to_list(None)
    users_with_failed_payments = result_failed_payments[0]["users_with_failed_payments"] if result_failed_payments and \
                                                                                            result_failed_payments[
                                                                                                0].get(
                                                                                                "users_with_failed_payments") is not None else 0
    percentage_failed_payments = (users_with_failed_payments / total_users * 100) if total_users > 0 else 0

    revenue_per_generation = total_revenue / total_generations if total_generations > 0 else 0

    pipeline_within_1_day = [{"$match": {"first_generation_time": {"$exists": True}, "registered_at": {"$exists": True},
                                         "first_generation_time": {
                                             "$lte": {"$add": ["$registered_at", 24 * 60 * 60 * 1000]}}}},
                             {"$count": "users_within_1_day"}]
    result_within_1_day = await users_collection.aggregate(pipeline_within_1_day).to_list(None)
    users_within_1_day = result_within_1_day[0]["users_within_1_day"] if result_within_1_day and result_within_1_day[
        0].get("users_within_1_day") is not None else 0
    percentage_within_1_day = (users_within_1_day / total_users * 100) if total_users > 0 else 0

    pipeline_within_7_days = [{
        "$match": {"first_generation_time": {"$exists": True}, "registered_at": {"$exists": True},
                   "first_generation_time": {"$lte": {"$add": ["$registered_at", 7 * 24 * 60 * 60 * 1000]}}}},
        {"$count": "users_within_7_days"}]
    result_within_7_days = await users_collection.aggregate(pipeline_within_7_days).to_list(None)
    users_within_7_days = result_within_7_days[0]["users_within_7_days"] if result_within_7_days and \
                                                                            result_within_7_days[0].get(
                                                                                "users_within_7_days") is not None else 0
    percentage_within_7_days = (users_within_7_days / total_users * 100) if total_users > 0 else 0

    pipeline_within_30_days = [{
        "$match": {"first_generation_time": {"$exists": True}, "registered_at": {"$exists": True},
                   "first_generation_time": {"$lte": {"$add": ["$registered_at", 30 * 24 * 60 * 60 * 1000]}}}},
        {"$count": "users_within_30_days"}]
    result_within_30_days = await users_collection.aggregate(pipeline_within_30_days).to_list(None)
    users_within_30_days = result_within_30_days[0]["users_within_30_days"] if result_within_30_days and \
                                                                               result_within_30_days[0].get(
                                                                                   "users_within_30_days") is not None else 0
    percentage_within_30_days = (users_within_30_days / total_users * 100) if total_users > 0 else 0

    logger.info("Статистика успешно собрана.")
    return {"total_users": total_users, "total_generations": total_generations, "total_revenue": total_revenue,
            "active_users_last_7_days": active_users,
            "average_time_to_first_generation_hours": round(avg_time_to_first_gen_hours, 2),
            "percentage_users_with_zero_generations": round(percentage_zero_generations, 2),
            "average_payment_amount": round(average_payment, 2),
            "percentage_repeat_payments": round(percentage_repeat_payments, 2),
            "average_payments_per_paying_user": round(average_payments_per_paying_user, 2),
            "average_activity_depth_days": round(avg_activity_depth_days, 2),
            "percentage_users_with_high_ltv": round(percentage_high_ltv, 2),
            "average_time_between_generations_days": round(avg_time_between_days, 2),
            "percentage_users_with_payment_errors": round(percentage_failed_payments, 2),
            "revenue_per_generation": round(revenue_per_generation, 2),
            "percentage_first_generation_within_1_day": round(percentage_within_1_day, 2),
            "percentage_first_generation_within_7_days": round(percentage_within_7_days, 2),
            "percentage_first_generation_within_30_days": round(percentage_within_30_days, 2), }


@router.get("/source_statistics", dependencies=[Depends(get_api_key_dependency)])
async def get_source_statistics_endpoint():
    """Возвращает статистику по пользователям и генерациям, сгруппированную по рекламным источникам."""
    if not users_collection or not advertising_sources_collection:
        logger.warning("Запрос статистики по источникам при недоступных коллекциях пользователей и источников")
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")

    pipeline = [{"$group": {"_id": "$advertising_source", "user_count": {"$sum": 1},
                            "total_generations": {"$sum": "$generation_count"},
                            "users_with_generations": {"$sum": {"$cond": [{"$gt": ["$generation_count", 0]}, 1, 0]}}}},
                {"$lookup": {"from": advertising_sources_collection.name, "localField": "_id",
                             "foreignField": "source_code", "as": "source_info"}},
                {"$unwind": {"path": "$source_info", "preserveNullAndEmptyArrays": True}}, {
                    "$project": {"source_code": "$_id",
                                 "campaign_name": {"$ifNull": ["$source_info.campaign_name", "Неизвестно"]},
                                 "user_count": 1, "total_generations": 1, "users_with_generations": 1}}]
    result = await users_collection.aggregate(pipeline).to_list(None)
    logger.info("Статистика по источникам успешно собрана.")
    return result


@router.get("/users/{chat_id}", response_model=User, dependencies=[Depends(get_api_key_dependency)])
async def get_user_endpoint(chat_id: int):
    """Возвращает информацию о пользователе по его ID в чате."""
    user = await get_db_user(chat_id)
    if not user:
        logger.warning(f"Попытка получить несуществующего пользователя: {chat_id}")
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    await update_last_activity(chat_id)
    user.pop("_id", None)
    logger.info(f"Получена информация о пользователе: {chat_id}")
    return User(**user)


@router.post("/generate", response_model=GenerationResponse, dependencies=[Depends(get_api_key_dependency)])
async def generate_drawing_endpoint(chat_id: int = Form(...), image: UploadFile = File(...)):
    """Принимает изображение от пользователя и генерирует на его основе новые изображения."""
    image_data = await image.read()
    if not image_data:
        logger.warning(f"Пользователь {chat_id} загрузил пустое изображение.")
        raise HTTPException(status_code=400, detail="Загруженное изображение пустое")

    response = await generate_images_service(chat_id, image_data)
    await update_last_activity(chat_id)
    return response


@router.post("/users/{chat_id}/create_payment", dependencies=[Depends(get_api_key_dependency)])
async def create_payment_endpoint(chat_id: int, payment_data: PaymentRequestBody):
    """Создает платежную ссылку YooKassa для указанного пользователя и информации о покупке."""
    response = await create_yookassa_payment_service(chat_id, payment_data.item_name, payment_data.quantity,
                                                     payment_data.price)
    await update_last_activity(chat_id)
    return response


@router.post("/users/{chat_id}/add_ozhivashki/{amount}", dependencies=[Depends(get_api_key_dependency)])
async def add_ozhivashki_endpoint(chat_id: int, amount: int):
    """Добавляет указанное количество 'оживашек' пользователю. (Административная функция)"""
    if not users_collection:
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Количество должно быть положительным")
    result = await users_collection.update_one({"chat_id": chat_id}, {"$inc": {"ozhivashki": amount}})
    if result.matched_count == 0:
        logger.warning(f"Попытка добавить оживашки несуществующему пользователю: {chat_id}")
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    logger.info(f"Добавлено {amount} оживашек пользователю {chat_id} через API.")
    await update_last_activity(chat_id)
    return {"message": f"{amount} оживашек успешно добавлено."}


@router.post("/users/{chat_id}/claim_daily_bonus", dependencies=[Depends(get_api_key_dependency)])
async def claim_daily_bonus_endpoint(chat_id: int):
    """Позволяет пользователю получить ежедневный бонус, если он доступен."""
    if not users_collection:
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")

    user = await get_db_user(chat_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user.get("daily_bonus_claimed_today", False):
        raise HTTPException(status_code=400, detail="Ежедневный бонус уже получен сегодня.")

    registered_at = user.get("registered_at")
    if not registered_at or not isinstance(registered_at, datetime):
        logger.error(f"Неверная дата регистрации для пользователя {chat_id}: {registered_at}")
        raise HTTPException(status_code=400, detail="Дата регистрации не найдена или некорректна.")

    days_since_registration = (datetime.now() - registered_at).days

    if days_since_registration >= 3:
        raise HTTPException(status_code=400, detail="Период получения ежедневного бонуса истек (только первые 3 дня).")

    ozhivashki_added = 1
    await users_collection.update_one({"chat_id": chat_id}, {"$inc": {"ozhivashki": ozhivashki_added},
                                                             "$set": {"daily_bonus_claimed_today": True,
                                                                      "last_activity_time": datetime.now()}})
    logger.info(
        f"Пользователь {chat_id} получил ежедневный бонус ({ozhivashki_added} оживашка). Дней с момента регистрации: {days_since_registration}")
    return {"message": "Ежедневный бонус получен!", "ozhivashki_added": ozhivashki_added}


@router.put("/users/{chat_id}/mark_discount_offered", dependencies=[Depends(get_api_key_dependency)])
async def mark_discount_offered_endpoint(chat_id: int):
    """Отмечает, что пользователю было предложено специальное предложение или скидка."""
    if not users_collection:
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")
    result = await users_collection.update_one({"chat_id": chat_id}, {
        "$set": {"discount_offered": True, "last_activity_time": datetime.now()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    logger.info(f"Скидка отмечена как предложенная для пользователя {chat_id}")
    return {"message": "Скидка отмечена как предложенная."}


@router.post("/tasks/reset_daily_bonus_flags", dependencies=[Depends(get_api_key_dependency)])
async def reset_daily_bonus_flags_endpoint():
    """Сбрасывает флаг получения ежедневного бонуса для всех пользователей (обычно запускается по расписанию)."""
    if not users_collection:
        raise HTTPException(status_code=503, detail="Сервис базы данных недоступен")
    try:
        result = await users_collection.update_many({"daily_bonus_claimed_today": True},
                                                    {"$set": {"daily_bonus_claimed_today": False}})
        logger.info(f"Сброшен флаг получения ежедневного бонуса для {result.modified_count} пользователей.")
        return {"message": f"Сброшен флаг получения ежедневного бонуса для {result.modified_count} пользователей."}
    except Exception as e:
        logger.error(f"Ошибка при сбросе флагов ежедневного бонуса: {e}")
        raise HTTPException(status_code=500, detail="Не удалось сбросить флаги ежедневного бонуса.")
