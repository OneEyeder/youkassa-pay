import asyncio
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

from db import create_payment_record, get_payment, set_payment_status
from yookassa_client import YooKassaConfig, configure_yookassa, create_payment, get_payment_status

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "app.db")

SUBSCRIPTION_FILE = os.environ.get("SUBSCRIPTION_FILE", "subscription.txt")
PRICE_RUB = "299.00"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def _require_env(name: str, value: str) -> None:
    if not value:
        raise RuntimeError(f"Missing env var: {name}")


@dp.message(CommandStart())
async def start(message: Message) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 299 ₽", callback_data="pay_299")]
        ]
    )
    await message.answer("Нажми кнопку, чтобы оплатить подписку.", reply_markup=kb)


@dp.callback_query(F.data == "pay_299")
async def pay_299(callback_query) -> None:
    _require_env("BOT_TOKEN", BOT_TOKEN)
    _require_env("YOOKASSA_SHOP_ID", YOOKASSA_SHOP_ID)
    _require_env("YOOKASSA_SECRET_KEY", YOOKASSA_SECRET_KEY)
    _require_env("PUBLIC_BASE_URL", PUBLIC_BASE_URL)

    configure_yookassa(YooKassaConfig(shop_id=YOOKASSA_SHOP_ID, secret_key=YOOKASSA_SECRET_KEY))

    telegram_id = callback_query.from_user.id
    return_url = f"{PUBLIC_BASE_URL.rstrip('/')}/return"

    payment = create_payment(
        amount_rub=PRICE_RUB,
        description="Подписка",
        return_url=return_url,
        telegram_id=telegram_id,
    )
    print(f"[DEBUG] YooKassa response: {payment}")

    payment_id = payment.id
    confirmation_url = payment.confirmation.confirmation_url
    if not payment_id or not confirmation_url:
        await callback_query.message.answer(f"Ошибка создания платежа. Ответ: {payment}")
        return

    created_at = datetime.now(timezone.utc).isoformat()
    create_payment_record(SQLITE_PATH, payment_id, telegram_id, "pending", created_at)

    # Запускаем фоновую задачу для проверки статуса
    asyncio.create_task(_poll_payment_status(payment_id, telegram_id, callback_query.message))

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Перейти к оплате", url=confirmation_url)]]
    )
    await callback_query.message.answer("Оплати по ссылке, затем дождись файла в этом чате.", reply_markup=kb)
    await callback_query.answer()


async def _poll_payment_status(payment_id: str, telegram_id: int, message) -> None:
    """Проверяет статус платежа каждые 5 секунд, пока не получим succeeded"""
    configure_yookassa(YooKassaConfig(shop_id=YOOKASSA_SHOP_ID, secret_key=YOOKASSA_SECRET_KEY))
    
    for _ in range(60):  # Максимум 5 минут (60 * 5 сек)
        await asyncio.sleep(5)
        
        try:
            payment = get_payment_status(payment_id)
            print(f"[POLL] Payment {payment_id} status: {payment.status}")
            
            if payment.status == "succeeded":
                # Проверяем, не отправляли ли уже файл
                row = get_payment(SQLITE_PATH, payment_id)
                if row is not None and row[2] == "succeeded":
                    return
                
                set_payment_status(SQLITE_PATH, payment_id, "succeeded")
                
                if not os.path.exists(SUBSCRIPTION_FILE):
                    await message.answer("Платёж прошёл, но файл не найден на сервере.")
                    return
                
                await message.answer_document(
                    FSInputFile(SUBSCRIPTION_FILE, filename=os.path.basename(SUBSCRIPTION_FILE)),
                    caption="Вот твоя подписка и код",
                )
                return
                
            elif payment.status in ["canceled", "expired"]:
                await message.answer("Платёж отменён или истёк.")
                return
                
        except Exception as e:
            print(f"[POLL] Error checking payment {payment_id}: {e}")
            continue
    
    # Таймаут
    await message.answer("Время ожидания оплаты истекло. Если вы оплатили, напишите администратору.")
