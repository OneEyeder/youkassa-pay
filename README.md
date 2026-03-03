# Telegram бот + ЮKassa (aiogram v3 + FastAPI)

## Зачем тут FastAPI
ЮKassa сообщает о результате оплаты через **webhook**: после успешной/отменённой оплаты ЮKassa делает HTTP POST на ваш сервер.

- Если принимать webhook, бот **сразу и надёжно** узнаёт, что платёж `succeeded`.
- Без webhook остаётся только **опрос** (polling) ЮKassa API по `payment_id`, что менее удобно и может быть ненадёжно.

В этом проекте FastAPI поднимает HTTP endpoint `/yookassa/webhook`, а aiogram работает в том же процессе (uvicorn запускает всё вместе).

## Что нужно подготовить
1. Создать Telegram-бота у @BotFather и получить `BOT_TOKEN`.
2. Зарегистрироваться в ЮKassa и получить:
   - `shopId`
   - `secretKey`
3. Сделать ваш сервер доступным по **публичному HTTPS URL** для webhook.
   - Для разработки можно использовать `ngrok`.

## Настройка `.env`
Скопируйте `.env.example` в `.env` и заполните:
- `BOT_TOKEN`
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `PUBLIC_BASE_URL` (например `https://xxxx.ngrok-free.app`)
- `RETURN_URL` (куда вернётся пользователь после оплаты)

Опционально:
- `TAX_SYSTEM_CODE` (1..6)
- `ITEM_DESCRIPTION`

## Установка
```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
```

## Запуск
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Использование
- В Telegram: `/start`
- Затем: `/buy`
- Бот попросит email для чека, затем отправит ссылку на оплату.

## Важно про webhook в ЮKassa
В личном кабинете ЮKassa нужно добавить уведомления (webhook) на:

`{PUBLIC_BASE_URL}/yookassa/webhook`

События:
- `payment.succeeded`
- `payment.canceled`

## Про чек (54‑ФЗ)
В примере формируется `receipt` с:
- `customer.email`
- 1 позиция
- `vat_code=1` (НДС не облагается)

Под ваши требования НДС/предмет расчёта/признак способа расчёта могут отличаться — это надо привести в соответствие вашему кейсу.
