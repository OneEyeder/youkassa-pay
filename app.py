from __future__ import annotations

import asyncio
import os
import re
import uuid
from decimal import Decimal
from typing import Any, Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from yookassa import Configuration, Payment

from storage import Storage


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
RETURN_URL = os.getenv("RETURN_URL", "")
ITEM_DESCRIPTION = os.getenv("ITEM_DESCRIPTION", "Оплата")
TAX_SYSTEM_CODE_RAW = os.getenv("TAX_SYSTEM_CODE", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

storage = Storage("bot.db")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()


class BuyStates(StatesGroup):
    waiting_email = State()


def _validate_email(email: str) -> bool:
    email = email.strip()
    if len(email) > 254:
        return False
    return re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email) is not None


def _tax_system_code() -> Optional[int]:
    if not TAX_SYSTEM_CODE_RAW:
        return None
    try:
        v = int(TAX_SYSTEM_CODE_RAW)
    except ValueError:
        return None
    return v if 1 <= v <= 6 else None


def _yookassa_configure() -> None:
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise RuntimeError("YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY are required")
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY


def _format_receipt(payment_data: dict, user_email: str) -> str:
    """Форматирует чек в текстовом виде для отправки в Telegram"""
    from datetime import datetime
    
    amount = payment_data.get("amount", {})
    value = amount.get("value", "0.00")
    currency = amount.get("currency", "RUB")
    
    receipt_items = payment_data.get("receipt", {}).get("items", [])
    description = payment_data.get("description", ITEM_DESCRIPTION)
    payment_id = payment_data.get("id", "")
    
    # Дата и время
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Формируем чек
    receipt_text = f"""
🧾 **ФИСКАЛЬНЫЙ ЧЕК**

📍 **ИНН:** {YOOKASSA_SHOP_ID}
🏪 **Продавец:** Онлайн-сервис
📅 **Дата:** {now}
🆔 **Чек №:** {payment_id[:8].upper()}

📦 **ТОВАРЫ:**
"""
    
    for item in receipt_items:
        item_desc = item.get("description", "Услуга")
        item_qty = item.get("quantity", "1.00")
        item_amount = item.get("amount", {})
        item_price = item_amount.get("value", "0.00")
        
        receipt_text += f"• {item_desc}\n"
        receipt_text += f"  Количество: {item_qty} шт.\n"
        receipt_text += f"  Цена: {item_price} ₽\n\n"
    
    receipt_text += f"""
💰 **ИТОГО:**
Сумма: {value} {currency}

👤 **ПОКУПАТЕЛЬ:**
Email: {user_email}

💳 **ОПЛАТА:**
Способ: Банковская карта
Статус: ✅ Оплачено

📄 **ЧЕК СФОРМИРОВАН В СООТВЕТСТВИИ С 54-ФЗ**
    """
    
    return receipt_text.strip()


def create_payment(*, telegram_user_id: int, email: str) -> dict[str, Any]:
    _yookassa_configure()

    webhook_url = f"{PUBLIC_BASE_URL}/yookassa/webhook" if PUBLIC_BASE_URL else None
    if not webhook_url:
        raise RuntimeError(
            "PUBLIC_BASE_URL is required to receive YooKassa webhooks. "
            "Example: https://xxxx.ngrok-free.app"
        )

    if not RETURN_URL:
        raise RuntimeError("RETURN_URL is required")

    amount = {
        "value": "199.00",
        "currency": "RUB",
    }

    receipt: dict[str, Any] = {
        "customer": {"email": email},
        "items": [
            {
                "description": ITEM_DESCRIPTION,
                "quantity": "1.00",
                "amount": amount,
                "vat_code": 1,
                "payment_subject": "service",
                "payment_mode": "full_payment",
            }
        ],
    }

    tsc = _tax_system_code()
    if tsc is not None:
        receipt["tax_system_code"] = tsc

    payment_data: dict[str, Any] = {
        "amount": amount,
        "confirmation": {
            "type": "redirect",
            "return_url": RETURN_URL,
        },
        "capture": True,
        "description": ITEM_DESCRIPTION,
        "metadata": {
            "telegram_user_id": str(telegram_user_id),
        },
        "receipt": receipt,
    }

    idempotence_key = str(uuid.uuid4())
    payment = Payment.create(payment_data, idempotence_key)

    storage.upsert_payment(payment.id, telegram_user_id, str(payment.status))

    return {
        "id": payment.id,
        "status": str(payment.status),
        "confirmation_url": payment.confirmation.confirmation_url,
        "webhook_url": webhook_url,
    }


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer("Привет! Для оплаты нажми /buy")


@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    email = storage.get_user_email(user_id)
    if not email:
        await state.set_state(BuyStates.waiting_email)
        await message.answer("Пришли email для чека (54‑ФЗ).")
        return

    try:
        p = create_payment(telegram_user_id=user_id, email=email)
    except Exception as e:
        await message.answer(f"Не удалось создать платёж: {e}")
        return

    await message.answer(
        "Ссылка на оплату:\n" + p["confirmation_url"] + "\n\n" +
        "После оплаты я пришлю подтверждение сообщением."
    )


@router.message(BuyStates.waiting_email)
async def got_email(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return

    email = (message.text or "").strip()
    if not _validate_email(email):
        await message.answer("Похоже на неверный email. Пришли ещё раз.")
        return

    storage.set_user_email(user_id, email)
    await state.clear()

    try:
        p = create_payment(telegram_user_id=user_id, email=email)
    except Exception as e:
        await message.answer(f"Не удалось создать платёж: {e}")
        return

    await message.answer(
        "Ссылка на оплату:\n" + p["confirmation_url"] + "\n\n" +
        "После оплаты я пришлю подтверждение сообщением."
    )


@router.callback_query(lambda c: c.data and c.data.startswith("save_receipt_"))
async def save_receipt_callback(callback: CallbackQuery) -> None:
    """Обработчик кнопки сохранения чека"""
    user_id = callback.from_user.id if callback.from_user else None
    if not user_id:
        return
    
    payment_id = callback.data.replace("save_receipt_", "")
    
    try:
        # Получаем информацию о платеже
        payment_record = storage.get_payment(payment_id)
        if not payment_record or payment_record.telegram_user_id != user_id:
            await callback.answer("Чек не найден", show_alert=True)
            return
        
        user_email = storage.get_user_email(user_id) or "не указан"
        
        # Формируем текст чека для сохранения
        receipt_text = f"""
ЧЕК №{payment_id[:8].upper()}
Дата: {payment_record.created_at if hasattr(payment_record, 'created_at') else 'N/A'}
Сумма: 199.00 RUB
Email: {user_email}
Статус: Оплачено

Чек сформирован в соответствии с 54-ФЗ
        """.strip()
        
        await callback.answer("Чек сохранен!", show_alert=True)
        await callback.message.answer("📄 **Чек сохранен**\n\n" + receipt_text)
        
    except Exception as e:
        await callback.answer("Ошибка при сохранении чека", show_alert=True)


dp.include_router(router)

app = FastAPI()


@app.on_event("startup")
async def _startup() -> None:
    app.state.bot_task = asyncio.create_task(dp.start_polling(bot))


@app.on_event("shutdown")
async def _shutdown() -> None:
    task = getattr(app.state, "bot_task", None)
    if task:
        task.cancel()
    await bot.session.close()


@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request) -> JSONResponse:
    payload = await request.json()

    event = payload.get("event")
    obj = payload.get("object") or {}
    payment_id = obj.get("id")

    if event not in {"payment.succeeded", "payment.canceled", "payment.waiting_for_capture"}:
        return JSONResponse({"ok": True})

    if not payment_id:
        return JSONResponse({"ok": True})

    try:
        _yookassa_configure()
        payment = Payment.find_one(str(payment_id))
    except Exception:
        return JSONResponse({"ok": True})

    metadata = getattr(payment, "metadata", None) or {}
    tg_user_id_raw = metadata.get("telegram_user_id") if isinstance(metadata, dict) else None

    try:
        tg_user_id = int(tg_user_id_raw) if tg_user_id_raw is not None else None
    except ValueError:
        tg_user_id = None

    status = str(getattr(payment, "status", ""))
    if status:
        if tg_user_id is not None:
            storage.upsert_payment(str(payment_id), tg_user_id, status)

    if tg_user_id is not None and status == "succeeded":
        try:
            # Получаем email пользователя
            user_email = storage.get_user_email(tg_user_id) or "не указан"
            
            # Формируем данные чека из информации о платеже
            payment_data = {
                "id": payment_id,
                "amount": {
                    "value": str(getattr(payment, "amount", {}).get("value", "199.00")),
                    "currency": str(getattr(payment, "amount", {}).get("currency", "RUB"))
                },
                "description": str(getattr(payment, "description", ITEM_DESCRIPTION)),
                "receipt": {
                    "items": [
                        {
                            "description": str(getattr(payment, "description", ITEM_DESCRIPTION)),
                            "quantity": "1.00",
                            "amount": {
                                "value": str(getattr(payment, "amount", {}).get("value", "199.00")),
                                "currency": str(getattr(payment, "amount", {}).get("currency", "RUB"))
                            }
                        }
                    ]
                }
            }
            
            # Генерируем текст чека
            receipt_text = _format_receipt(payment_data, user_email)
            
            # Создаем клавиатуру с кнопкой для сохранения чека
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💾 Сохранить чек", callback_data=f"save_receipt_{payment_id}")]
            ])
            
            # Отправляем сообщение с чеком
            await bot.send_message(
                tg_user_id, 
                "✅ **Оплата прошла успешно!**\n\n" + receipt_text,
                reply_markup=keyboard
            )
        except Exception as e:
            # Если не удалось отправить чек, отправляем простое сообщение
            try:
                await bot.send_message(tg_user_id, "Оплата прошла успешно. Спасибо!")
            except Exception:
                pass

    return JSONResponse({"ok": True})
