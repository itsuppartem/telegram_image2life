import asyncio
import os
import uuid
from datetime import datetime
from typing import Union

import httpx
from aiogram import F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
                           InputMediaPhoto, FSInputFile)

from .config import (router, bot, logger, API_URL, API_KEY, CURRENCY_NAME, CURRENCY_NAME_PLURAL_2_4,
                     CURRENCY_NAME_PLURAL_5_0, CURRENCY_NAME_PLURAL_6_0, EMOJI_SPARKLES, EMOJI_CAMERA, EMOJI_MAGIC_WAND,
                     EMOJI_ROBOT, EMOJI_GIFT, EMOJI_STAR, EMOJI_PENCIL, EMOJI_MONEY, EMOJI_HOME,
                     EMOJI_HOURGLASS, EMOJI_INFO, EMOJI_SAD, EMOJI_THINKING,
                     EMOJI_POINT_DOWN, EMOJI_PARTY, EMOJI_HEART, EMOJI_CHILD,
                     EMOJI_CALENDAR, EXAMPLE_IMAGE_PATHS)
from .states import OzhivlyatorState
from .utils import (pluralize_ozhivashki, safe_delete_message, send_or_edit_message, get_user_data, create_user)


async def show_main_menu(target: Union[Message, CallbackQuery], state: FSMContext):
    if isinstance(target, CallbackQuery):
        chat_id = target.message.chat.id
        message_id_to_edit = target.message.message_id
        try:
            await target.answer()
        except TelegramBadRequest:
            pass
    else:
        chat_id = target.chat.id
        state_data = await state.get_data()
        message_id_to_edit = state_data.get('last_bot_message_id')
        await safe_delete_message(chat_id, target.message_id)

    user_data = await get_user_data(chat_id)
    if not user_data:
        await send_or_edit_message(chat_id, f"{EMOJI_SAD} Не могу загрузить твои данные. Попробуй /start снова.",
                                   edit_message_id=message_id_to_edit, state=state)
        await state.clear()
        return

    balance = user_data.get("ozhivashki", 0)
    balance_text = f"{balance} {pluralize_ozhivashki(balance)}"

    menu_text = f"{EMOJI_MAGIC_WAND} Готов оживлять рисунки!\n\n"
    menu_text += f"Твой баланс: <b>{balance_text}</b> {EMOJI_GIFT}\n\n"

    keyboard_rows = []

    if balance > 0:
        menu_text += f"{EMOJI_POINT_DOWN} Нажми Оживить рисунок или отправь мне фото!"
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"{EMOJI_PENCIL} Оживить рисунок", callback_data="generate_drawing")])
    else:
        menu_text += f"{EMOJI_SAD} Оживашки закончились! Нужно пополнить баланс."

    keyboard_rows.append([InlineKeyboardButton(text=f"{EMOJI_MONEY} Купить оживашки", callback_data="buy_ozhivashki")])
    keyboard_rows.append([InlineKeyboardButton(text=f"{EMOJI_GIFT} Бонусы", callback_data="show_bonuses")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await send_or_edit_message(chat_id, menu_text, reply_markup, state, message_id_to_edit)
    await state.set_state(OzhivlyatorState.main_menu)
    logger.info(f"Displayed main menu for user {chat_id}. Balance: {balance}")


@router.message(Command(commands=["start"]))
async def cmd_start(message: Message, state: FSMContext):
    chat_id = message.chat.id
    username = message.from_user.username
    args = message.text.split()
    param = args[1] if len(args) > 1 else None
    referral_code = param if param and param.startswith("ref_") else None
    source_code = param if param and param.startswith("src_") else None

    logger.info(f"/start от {chat_id} ({username}). Referral: {referral_code}, Source: {source_code}")

    state_data = await state.get_data()
    last_msg_id = state_data.get('last_bot_message_id')
    if last_msg_id:
        await safe_delete_message(chat_id, last_msg_id)
    await state.clear()

    user_data = await get_user_data(chat_id)
    if not user_data:
        user_data = await create_user(chat_id, username, referral_code, source_code)
        if not user_data:
            await message.answer(f"{EMOJI_SAD} Ошибка при создании профиля. Попробуй /start позже.")
            return

        welcome_text = (
            f"Привет! {EMOJI_MAGIC_WAND} Я Оживлятор - бот, который превращает детские рисунки в волшебные картины!\n\n"
            f"У тебя есть <b>1 бесплатная {CURRENCY_NAME}</b>, чтобы попробовать!\n\n")
        if referral_code:
            welcome_text += (f"{EMOJI_CHILD} Ты пришел по приглашению друга! "
                             f"После твоей первой генерации твой друг получит <b>2 {CURRENCY_NAME_PLURAL_2_4}</b>.\n\n")
        welcome_text += (f"{EMOJI_PENCIL} Отправь мне фото рисунка, и я создам 4 оживших варианта.\n\n"
                         f"Смотри, как это может выглядеть:")
        await message.answer(welcome_text)

        try:
            media_group = []
            for i, img_path in enumerate(EXAMPLE_IMAGE_PATHS):
                if os.path.exists(img_path):
                    if i == 0:
                        media_group.append(
                            InputMediaPhoto(media=FSInputFile(img_path), caption="Примеры оживленных рисунков"))
                    else:
                        media_group.append(InputMediaPhoto(media=FSInputFile(img_path)))
                else:
                    logger.warning(f"Example image not found: {img_path}")
            if media_group:
                await message.answer_media_group(media=media_group)
        except Exception as e:
            logger.error(f"Error sending example images: {e}")

        await show_main_menu(message, state)
    else:
        if user_data.get("ozhivashki", 0) == 0 and referral_code and user_data.get("generation_count", 0) == 1:
            await message.answer(f"{EMOJI_INFO} Ты пришел по приглашению друга и уже сделал первую генерацию. "
                                 f"Твой друг получил 2 {CURRENCY_NAME_PLURAL_2_4}. "
                                 f"Пополни баланс, чтобы продолжить оживлять рисунки!")
        await show_main_menu(message, state)


@router.message(Command(commands=["help"]))
async def cmd_help(message: Message, state: FSMContext):
    await safe_delete_message(message.chat.id, message.message_id)
    state_data = await state.get_data()
    last_msg_id = state_data.get('last_bot_message_id')

    help_text = (f"{EMOJI_INFO} <b>Как пользоваться ботом:</b>\n\n"
                 f"1. Нажми кнопку {EMOJI_PENCIL} Оживить рисунок (если у тебя есть {CURRENCY_NAME_PLURAL_5_0}).\n"
                 f"2. Отправь мне фотографию детского рисунка {EMOJI_CAMERA}.\n"
                 f"3. Подожди немного, пока я творю магию {EMOJI_HOURGLASS}.\n"
                 f"4. Я пришлю тебе 4 оживших варианта рисунка!\n\n"
                 f"{EMOJI_GIFT} <b>Бонусы:</b>\n"
                 f"- Первая генерация получает +2 бонусных фото.\n"
                 f"- Каждая 2-я генерация получает +2 бонусных фото.\n"
                 f"- Каждая 5 генерация - не расходует {CURRENCY_NAME_PLURAL_6_0}.\n"
                 f"- Приглашай друзей и получай {CURRENCY_NAME_PLURAL_2_4}!\n\n"
                 f"{EMOJI_MONEY} Если {CURRENCY_NAME_PLURAL_5_0} закончатся, их можно купить.")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"{EMOJI_HOME} В главное меню", callback_data="go_main_menu")]])
    await send_or_edit_message(message.chat.id, help_text, kb, state, last_msg_id)

    current_state = await state.get_state()
    if current_state != OzhivlyatorState.main_menu:
        await state.set_state(OzhivlyatorState.main_menu)


@router.message(Command(commands=["bonus"]))
async def cmd_bonus(message: Message, state: FSMContext):
    await safe_delete_message(message.chat.id, message.message_id)

    fake_query = CallbackQuery(id=str(uuid.uuid4()), from_user=message.from_user, chat_instance=message.chat.id,
                               message=None, data="show_bonuses")

    state_data = await state.get_data()
    last_msg_id = state_data.get('last_bot_message_id')
    if last_msg_id:

        dummy_msg = types.Message(message_id=last_msg_id, chat=message.chat, date=datetime.now())
        fake_query.message = dummy_msg
        await cb_show_bonuses(fake_query, state)
    else:

        await message.answer(f"{EMOJI_SAD} Не могу показать бонусы сейчас. Попробуй из главного меню.")
        await show_main_menu(message, state)


@router.callback_query(F.data == "go_main_menu", StateFilter("*"))
async def cb_go_main_menu(query: CallbackQuery, state: FSMContext):
    await show_main_menu(query, state)


@router.callback_query(F.data == "generate_drawing")
async def cb_generate_drawing(query: CallbackQuery, state: FSMContext):
    chat_id = query.message.chat.id
    user_data = await get_user_data(chat_id)
    if not user_data or user_data.get("ozhivashki", 0) <= 0:
        await query.answer(f"У тебя нет {CURRENCY_NAME_PLURAL_5_0}!", show_alert=True)
        await show_main_menu(query, state)
        return

    await query.answer("Жду твой рисунок...")
    text = f"{EMOJI_CAMERA} Отправь фотографию рисунка, который будем оживлять!"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"{EMOJI_HOME} Назад", callback_data="go_main_menu")]])
    message = await query.message.edit_text(text, reply_markup=kb)
    await state.update_data(message_to_delete=message.message_id)
    await state.set_state(OzhivlyatorState.waiting_for_drawing)


@router.callback_query(F.data == "buy_ozhivashki", StateFilter(OzhivlyatorState.main_menu))
async def cb_buy_ozhivashki(query: CallbackQuery, state: FSMContext):
    chat_id = query.message.chat.id
    await query.answer("Смотрю доступные пакеты...")

    user_data = await get_user_data(chat_id)
    show_discount = user_data.get("discount_offered", False) if user_data else False

    text = f"{EMOJI_MONEY} Выбери пакет {CURRENCY_NAME_PLURAL_5_0}:\n\n"
    keyboard_rows = []

    if show_discount:
        text += "Специальное предложение: скидка на пакет 10 оживашек!\n"
        keyboard_rows.append([InlineKeyboardButton(text="5 оживашек - 150 руб", callback_data="purchase:5")])
        keyboard_rows.append(
            [InlineKeyboardButton(text="10 оживашек - <s>250</s> 200 руб", callback_data="purchase:10_discount")])
    else:
        keyboard_rows.append([InlineKeyboardButton(text="5 оживашек - 150 руб", callback_data="purchase:5")])
        keyboard_rows.append([InlineKeyboardButton(text="10 оживашек - 250 руб", callback_data="purchase:10")])

    keyboard_rows.append([InlineKeyboardButton(text=f"{EMOJI_HOME} Назад", callback_data="go_main_menu")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await query.message.edit_text(text, reply_markup=reply_markup)
    await state.set_state(OzhivlyatorState.showing_purchase_options)


@router.callback_query(F.data.startswith("purchase:"), StateFilter(OzhivlyatorState.showing_purchase_options))
async def cb_initiate_purchase(query: CallbackQuery, state: FSMContext):
    ozhivashki_amount = 0
    price = 0.0
    item_name = ""
    package_key = query.data.split(":", 1)[1]
    chat_id = query.message.chat.id
    logger.info(f"User {chat_id} selected purchase package: {package_key}")
    try:
        if package_key == "5":
            ozhivashki_amount = 5
            price = 150.0
            item_name = "5 оживашек"
        elif package_key == "10":
            ozhivashki_amount = 10
            price = 250.0
            item_name = "10 оживашек"
        elif package_key == "10_discount":
            ozhivashki_amount = 10
            price = 200.0
            item_name = "10 оживашек (скидка)"
        else:
            raise ValueError("Неверный ключ пакета")

    except (ValueError, IndexError):
        logger.error(f"Invalid purchase package key '{package_key}' for user {chat_id}")
        await query.answer("Ошибка выбора пакета!", show_alert=True)
        await show_main_menu(query, state)
        return

    await query.answer(f"Создаю ссылку на оплату {item_name}...")

    async with httpx.AsyncClient(timeout=60) as client:
        payload = {"item_name": item_name, "quantity": ozhivashki_amount, "price": price}
        try:
            response = await client.post(f"{API_URL}/users/{chat_id}/create_payment", headers={"api-key": API_KEY},
                                         json=payload)
            response.raise_for_status()
            payment_data = response.json()
            payment_url = payment_data.get("payment_url")
            payment_id = payment_data.get("payment_id")

            if not payment_url:
                raise ValueError("API did not return payment URL")

            logger.info(f"Created payment link for {chat_id} ({item_name}): {payment_url}")

            text = (f"{EMOJI_MONEY} Отлично! Ты выбрал(а) <b>{item_name}</b> за {price:.0f} руб.\n\n"
                    f"{EMOJI_POINT_DOWN} Нажми кнопку ниже для безопасной оплаты через YooKassa:\n\n"
                    f"{EMOJI_INFO} После успешной оплаты {ozhivashki_amount} {pluralize_ozhivashki(ozhivashki_amount)} будут начислены <b>автоматически</b>.\n\n"
                    f"{EMOJI_HEART} Спасибо!")
            kb = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=f"💳 Оплатить {price:.0f} руб.", url=payment_url)], ])
            await query.message.edit_text(text, reply_markup=kb)

        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error creating payment for {chat_id}: Status {e.response.status_code}, Resp: {e.response.text[:100]}")
            error_text = f"{EMOJI_SAD} Ошибка создания ссылки на оплату. Попробуй позже."
            kb_err = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{EMOJI_HOME} В главное меню", callback_data="go_main_menu")]])
            await query.message.edit_text(error_text, reply_markup=kb_err)
            await state.set_state(OzhivlyatorState.main_menu)
        except Exception as e:
            logger.error(f"Unexpected error creating payment for {chat_id}: {e}")
            error_text = f"{EMOJI_SAD} Неизвестная ошибка при создании оплаты. Попробуй снова."
            kb_err = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{EMOJI_HOME} В главное меню", callback_data="go_main_menu")]])
            await query.message.edit_text(error_text, reply_markup=kb_err)
            await state.set_state(OzhivlyatorState.main_menu)


@router.callback_query(F.data == "show_bonuses", StateFilter(OzhivlyatorState.main_menu))
async def cb_show_bonuses(query: CallbackQuery, state: FSMContext):
    chat_id = query.message.chat.id
    await query.answer("Загружаю информацию о бонусах...")

    user_data = await get_user_data(chat_id)
    if not user_data:
        await query.message.edit_text(f"{EMOJI_SAD} Не могу загрузить данные. Попробуй позже.",
                                      reply_markup=InlineKeyboardMarkup([[
                                          InlineKeyboardButton(text=f"{EMOJI_HOME} Назад",
                                                               callback_data="go_main_menu")]]))
        return

    generation_count = user_data.get("generation_count", 0)
    daily_bonus_streak = user_data.get("daily_bonus_streak", 0)
    registered_at_str = user_data.get("registered_at")
    can_claim_daily = False
    days_since_registration = float('inf')

    if registered_at_str:
        try:
            registered_dt = datetime.fromisoformat(registered_at_str)
            days_since_registration = (datetime.now(registered_dt.tzinfo) - registered_dt).days
            if days_since_registration < 3 and not user_data.get("daily_bonus_claimed_today", False):
                can_claim_daily = True
        except ValueError:
            logger.warning(f"Could not parse registered_at for user {chat_id}: {registered_at_str}")

    bonus_text = f"{EMOJI_GIFT} <b>Бонусная программа:</b>\n\n"
    bonus_text += f"{EMOJI_MAGIC_WAND} <b>Бонусные фото:</b>\n"
    bonus_text += f"  - Первая генерация: +2 фото {EMOJI_PARTY}\n"
    bonus_text += f"  - Каждая 2-я генерация: +2 фото\n\n"

    bonus_text += f"{EMOJI_STAR} <b>Бонусные {CURRENCY_NAME_PLURAL_5_0}:</b>\n"
    bonus_text += f"  - Каждая 5 генерация не тратит {CURRENCY_NAME_PLURAL_6_0}\n"
    bonus_text += f"    <i>(Сделано генераций: {generation_count})</i>\n\n"

    if days_since_registration < 3:
        bonus_text += f"{EMOJI_CALENDAR} <b>Ежедневный бонус (первые 3 дня):</b>\n"
        if can_claim_daily:
            bonus_text += f"  - Нажми кнопку ниже, чтобы получить +1 {CURRENCY_NAME_PLURAL_6_0} сегодня!\n"
        elif user_data.get("daily_bonus_claimed_today", False):
            bonus_text += f"  - Ты уже получил(а) бонус сегодня! Приходи завтра.\n"
        else:
            pass
    bonus_text += "\n"

    referral_link = user_data.get("referral_link", "")
    if not referral_link:
        referral_code = f"ref_{chat_id}"
        bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "YOUR_BOT_USERNAME")
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"

    bonus_text += f"{EMOJI_CHILD} <b>Пригласи друга:</b>\n"
    bonus_text += f"  - Отправь другу ссылку:\n  {referral_link}\n"
    bonus_text += f"  - Получи <b>2 {CURRENCY_NAME_PLURAL_2_4}</b>, когда друг сделает первую генерацию!\n"

    keyboard_rows = []
    if can_claim_daily:
        keyboard_rows.append(
            [InlineKeyboardButton(text=f"{EMOJI_GIFT} Получить ежедневный бонус!", callback_data="claim_daily_bonus")])

    keyboard_rows.append([InlineKeyboardButton(text=f"{EMOJI_HOME} Назад", callback_data="go_main_menu")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    await query.message.edit_text(bonus_text, reply_markup=reply_markup, disable_web_page_preview=True)


@router.callback_query(F.data == "claim_daily_bonus", StateFilter(OzhivlyatorState.main_menu))
async def cb_claim_daily_bonus(query: CallbackQuery, state: FSMContext):
    chat_id = query.message.chat.id
    await query.answer(f"Проверяю возможность получить бонус...")

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.post(f"{API_URL}/users/{chat_id}/claim_daily_bonus", headers={"api-key": API_KEY})
            response_data = response.json()

            if response.status_code == 200:
                added = response_data.get("ozhivashki_added", 0)
                if added > 0:
                    logger.info(f"User {chat_id} claimed daily bonus ({added} ozhivashki).")
                    try:

                        new_text = f"\n\n{EMOJI_PARTY} Ура! +{added} {pluralize_ozhivashki(added)} добавлен(а) к твоему балансу!"
                        kb = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text=f"{EMOJI_HOME} В главное меню", callback_data="go_main_menu")]])

                        await query.message.edit_text(text=new_text, reply_markup=kb)
                        await state.set_state(OzhivlyatorState.main_menu)
                    except Exception as edit_err:

                        logger.error(f"Error editing message after successful bonus claim for {chat_id}: {edit_err}",
                                     exc_info=True)

                        try:
                            await query.answer(f"{EMOJI_PARTY} Бонус +{added} {pluralize_ozhivashki(added)} начислен!",
                                               show_alert=True)

                            await state.set_state(OzhivlyatorState.main_menu)
                        except Exception:
                            pass
                else:
                    logger.warning(f"API returned 200 but ozhivashki_added was {added} for user {chat_id}.")
                    await query.answer("Не удалось начислить бонус (ответ API 0).", show_alert=True)

                    await cb_show_bonuses(query, state)

            elif response.status_code == 400:
                error_msg = response_data.get("detail", "Бонус уже получен или недоступен.")
                await query.answer(error_msg, show_alert=True)
                logger.info(f"User {chat_id} failed to claim daily bonus: {error_msg}")

                await cb_show_bonuses(query, state)
            else:

                response.raise_for_status()

        except httpx.HTTPStatusError as e:

            logger.error(
                f"API error claiming daily bonus for {chat_id}: Status {e.response.status_code}, Resp: {e.response.text[:100]}")
            await query.answer(f"{EMOJI_SAD} Ошибка при получении бонуса (API). Попробуй позже.", show_alert=True)
        except Exception as e:

            logger.error(f"Unexpected error claiming daily bonus for {chat_id}: {e}", exc_info=True)
            await query.answer(f"{EMOJI_SAD} Неизвестная ошибка при получении бонуса. Попробуй позже.", show_alert=True)
            if query.message:
                await show_main_menu(query, state)
            else:
                await state.set_state(OzhivlyatorState.main_menu)


@router.message(F.photo)
async def msg_handle_drawing_upload(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        message_id = data.get("message_to_delete")

        if message_id:
            await bot.delete_message(chat_id=message.chat.id, message_id=message_id)
    except:
        pass
    chat_id = message.chat.id
    photo = message.photo[-1]
    file_id = photo.file_id
    logger.info(f"User {chat_id} uploaded drawing photo (file_id: {file_id})")

    state_data = await state.get_data()
    prompt_message_id = state_data.get('last_bot_message_id')

    user_data = await get_user_data(chat_id)
    if not user_data or user_data.get("ozhivashki", 0) <= 0:
        logger.warning(f"User {chat_id} tried to generate with 0 balance after uploading photo.")
        await message.answer(
            f"{EMOJI_SAD} Ой, похоже, {CURRENCY_NAME_PLURAL_5_0} закончились, пока ты загружал(а) рисунок!")
        await safe_delete_message(chat_id, message.message_id)
        if prompt_message_id: await safe_delete_message(chat_id, prompt_message_id)
        await show_main_menu(message, state)
        return

    processing_msg = await message.answer(f"{EMOJI_HOURGLASS} Магия началась... Оживляю рисунок!")
    await safe_delete_message(chat_id, message.message_id)
    if prompt_message_id: await safe_delete_message(chat_id, prompt_message_id)

    await state.set_state(OzhivlyatorState.processing_generation)

    async with httpx.AsyncClient(timeout=300) as client:
        try:
            file_info = await bot.get_file(file_id)
            file_bytes_io = await bot.download_file(file_info.file_path)
            file_bytes = file_bytes_io.read()

            if not file_bytes:
                raise ValueError("Downloaded file is empty")

            files = {'image': ('drawing.png', file_bytes, 'image/png')}
            response = await client.post(f"{API_URL}/generate", headers={"api-key": API_KEY}, files=files,
                                         data={"chat_id": chat_id})

            if response.status_code == 200:
                generation_result = response.json()
                main_images_b64 = generation_result.get("main_images", [])
                bonus_images_b64 = generation_result.get("bonus_images", [])
                ozhivashki_spent = generation_result.get("ozhivashki_spent", 0)
                new_balance = generation_result.get("new_balance")

                logger.info(
                    f"Generation successful for {chat_id}. Main: {len(main_images_b64)}, Bonus: {len(bonus_images_b64)}. Spent: {ozhivashki_spent}")

                await safe_delete_message(chat_id, processing_msg.message_id)

                if main_images_b64:
                    import base64
                    media_group_main = []
                    first = True
                    for i, img_b64 in enumerate(main_images_b64):
                        try:
                            img_bytes = base64.b64decode(img_b64)
                            if first:
                                media_group_main.append(
                                    InputMediaPhoto(media=BufferedInputFile(img_bytes, filename=f"result_{i + 1}.png"),
                                                    caption=f"{EMOJI_PARTY} Готово! Вот 4 оживших рисунка:"))
                                first = False
                            else:
                                media_group_main.append(
                                    InputMediaPhoto(media=BufferedInputFile(img_bytes, filename=f"result_{i + 1}.png")))
                        except Exception as decode_err:
                            logger.error(f"Error decoding/adding main image {i} for {chat_id}: {decode_err}")
                    if media_group_main:
                        await bot.send_media_group(chat_id=chat_id, media=media_group_main)
                    else:
                        await bot.send_message(chat_id, f"{EMOJI_SAD} Не удалось подготовить основные изображения.")
                else:
                    await bot.send_message(chat_id, f"{EMOJI_SAD} Не удалось сгенерировать основные изображения.")

                if bonus_images_b64:
                    await asyncio.sleep(1)
                    media_group_bonus = []
                    first_bonus = True
                    for i, img_b64 in enumerate(bonus_images_b64):
                        try:
                            img_bytes = base64.b64decode(img_b64)
                            if first_bonus:
                                media_group_bonus.append(
                                    InputMediaPhoto(media=BufferedInputFile(img_bytes, filename=f"bonus_{i + 1}.png"),
                                                    caption=f"{EMOJI_GIFT} А вот и бонусные 2 фото! Напоминаю, такой бонус дается за каждую 2-ю генерацию! {EMOJI_SPARKLES}"))
                                first_bonus = False
                            else:
                                media_group_bonus.append(
                                    InputMediaPhoto(media=BufferedInputFile(img_bytes, filename=f"bonus_{i + 1}.png")))
                        except Exception as decode_err:
                            logger.error(f"Error decoding/adding bonus image {i} for {chat_id}: {decode_err}")
                    if media_group_bonus:
                        await bot.send_media_group(chat_id=chat_id, media=media_group_bonus)

                referrer_id = user_data.get("referred_by")
                is_first_generation = user_data.get("generation_count", 0) == 0
                if referrer_id and is_first_generation:
                    try:
                        await bot.send_message(referrer_id,
                                               f"{EMOJI_PARTY} Твой друг только что сделал первую генерацию! "
                                               f"Тебе начислено <b>2 {CURRENCY_NAME_PLURAL_2_4}</b> за приглашение!")
                    except Exception as e:
                        logger.error(f"Failed to notify referrer {referrer_id}: {e}")

                if new_balance == 0:
                    await bot.send_message(chat_id,
                                           f"{EMOJI_INFO} Твоя бесплатная {CURRENCY_NAME} потрачена на эту генерацию. "
                                           f"Пополни баланс, чтобы оживить еще рисунки!")

                temp_msg = await bot.send_message(chat_id, "Обновляю меню...")
                await show_main_menu(temp_msg, state)

            elif response.status_code == 402:
                await safe_delete_message(chat_id, processing_msg.message_id)
                await bot.send_message(chat_id,
                                       f"{EMOJI_SAD} Упс! Не хватает {CURRENCY_NAME_PLURAL_5_0} для генерации.")
                await show_main_menu(message, state)
            else:
                response.raise_for_status()

        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error during generation for {chat_id}: Status {e.response.status_code}, Resp: {e.response.text[:100]}")
            await safe_delete_message(chat_id, processing_msg.message_id)
            await bot.send_message(chat_id,
                                   f"{EMOJI_SAD} Ошибка во время генерации.\nОживляшка не потрачена!\nПопробуй позже.")
            await show_main_menu(message, state)
        except ValueError as e:
            logger.error(f"Value error during generation for {chat_id}: {e}")
            await safe_delete_message(chat_id, processing_msg.message_id)
            await bot.send_message(chat_id,
                                   f"{EMOJI_SAD} Ошибка обработки изображения.\nОживляшка не потрачена!\nПопробуй другое фото.")
            await show_main_menu(message, state)
        except Exception as e:
            logger.error(f"Unexpected error during generation for {chat_id}: {e}", exc_info=True)
            await safe_delete_message(chat_id, processing_msg.message_id)
            await bot.send_message(chat_id,
                                   f"{EMOJI_SAD} Произошла неожиданная ошибка.\nОживляшка не потрачена!\nПопробуй позже.")
            await show_main_menu(message, state)
        finally:
            current_state = await state.get_state()
            if current_state != OzhivlyatorState.main_menu:
                await state.set_state(OzhivlyatorState.main_menu)


@router.message(StateFilter(OzhivlyatorState.waiting_for_drawing))
async def msg_wrong_content_type(message: Message, state: FSMContext):
    await safe_delete_message(message.chat.id, message.message_id)
    await message.answer(f"{EMOJI_THINKING} Пожалуйста, отправь именно фотографию рисунка {EMOJI_CAMERA}.",
                         reply_markup=InlineKeyboardMarkup(
                             [[InlineKeyboardButton(text=f"{EMOJI_HOME} Назад", callback_data="go_main_menu")]]))


@router.message(StateFilter("*"))
async def msg_unexpected(message: Message, state: FSMContext):
    current_state = await state.get_state()
    logger.warning(f"User {message.chat.id} sent unexpected message in state {current_state}: {message.text[:50]}")
    await safe_delete_message(message.chat.id, message.message_id)
    await message.answer(f"{EMOJI_ROBOT} Хм, я не совсем понял(а). Давай вернемся в главное меню.",
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text=f"{EMOJI_HOME} В главное меню",
                                                                                  callback_data="go_main_menu")]]))
    await state.set_state(OzhivlyatorState.main_menu)
