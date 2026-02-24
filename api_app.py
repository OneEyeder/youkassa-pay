import base64
import json
import os

from aiogram.types import FSInputFile
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response

from bot_app import bot
from db import get_payment, set_payment_status

load_dotenv()

WEBHOOK_BASIC_USER = os.environ.get("WEBHOOK_BASIC_USER", "")
WEBHOOK_BASIC_PASS = os.environ.get("WEBHOOK_BASIC_PASS", "")
SUBSCRIPTION_FILE = os.environ.get("SUBSCRIPTION_FILE", "subscription.txt")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "app.db")

app = FastAPI()


def _check_basic_auth(request: Request) -> None:
    if not WEBHOOK_BASIC_USER or not WEBHOOK_BASIC_PASS:
        raise RuntimeError("Missing WEBHOOK_BASIC_USER/WEBHOOK_BASIC_PASS")

    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("basic "):
        raise HTTPException(status_code=401)

    b64 = auth.split(" ", 1)[1].strip()
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=401)

    if ":" not in decoded:
        raise HTTPException(status_code=401)

    user, pw = decoded.split(":", 1)
    if user != WEBHOOK_BASIC_USER or pw != WEBHOOK_BASIC_PASS:
        raise HTTPException(status_code=401)


@app.get("/return")
async def return_page() -> Response:
    return Response(
        content="Оплата обрабатывается. Вернись в Telegram — файл придёт автоматически после подтверждения платежа.",
        media_type="text/plain; charset=utf-8",
    )


@app.post("/yookassa/webhook")
async def yookassa_webhook(request: Request) -> Response:
    body = await request.body()
    print(f"[WEBHOOK] Received request: {body}")
    # _check_basic_auth(request)  # временно отключено

    try:
        payload = json.loads(body)
    except Exception:
        return Response(status_code=400)
    event = payload.get("event")
    obj = payload.get("object") or {}

    if event != "payment.succeeded":
        return Response(status_code=200)

    payment_id = obj.get("id")
    if not payment_id:
        return Response(status_code=200)

    amount = (obj.get("amount") or {}).get("value")
    currency = (obj.get("amount") or {}).get("currency")
    if amount != "299.00" or currency != "RUB":
        return Response(status_code=200)

    status = obj.get("status")
    if status != "succeeded":
        return Response(status_code=200)

    metadata = obj.get("metadata") or {}
    telegram_id = metadata.get("telegram_id")

    if telegram_id is None:
        row = get_payment(SQLITE_PATH, payment_id)
        if row is None:
            return Response(status_code=200)
        telegram_id = row[1]

    try:
        telegram_id_int = int(telegram_id)
    except Exception:
        return Response(status_code=200)

    row = get_payment(SQLITE_PATH, payment_id)
    if row is not None and row[2] == "succeeded":
        return Response(status_code=200)

    set_payment_status(SQLITE_PATH, payment_id, "succeeded")

    if not os.path.exists(SUBSCRIPTION_FILE):
        await bot.send_message(telegram_id_int, "Платёж прошёл, но файл не найден на сервере. Напиши администратору.")
        return Response(status_code=200)

    await bot.send_document(
        telegram_id_int,
        FSInputFile(SUBSCRIPTION_FILE, filename=os.path.basename(SUBSCRIPTION_FILE)),
        caption="Вот твоя подписка и код",
    )

    return Response(status_code=200)
