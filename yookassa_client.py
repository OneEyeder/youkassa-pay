from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict
from uuid import uuid4

from yookassa import Configuration, Payment


@dataclass(frozen=True)
class YooKassaConfig:
    shop_id: str
    secret_key: str


def configure_yookassa(cfg: YooKassaConfig) -> None:
    Configuration.account_id = cfg.shop_id
    Configuration.secret_key = cfg.secret_key


def create_payment(*, amount_rub: str, description: str, return_url: str, telegram_id: int):
    idempotence_key = str(uuid4())

    payment = Payment.create(
        {
            "amount": {"value": amount_rub, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": {"telegram_id": str(telegram_id)},
        },
        idempotence_key,
    )

    return payment


def get_payment_status(payment_id: str):
    return Payment.find_one(payment_id)
