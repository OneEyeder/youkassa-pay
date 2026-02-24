# Telegram bot + YooKassa (299 RUB)

## Настройка

1) Создай файл `.env` на основе `.env.example`.

2) Установи зависимости:

```bash
pip install -r requirements.txt
```

3) Запусти приложение:

```bash
python main.py
```

## Ngrok (для webhook)

1) Запусти туннель:

```bash
ngrok http 8000
```

2) Возьми `https://...` URL и вставь в `.env` как `PUBLIC_BASE_URL`.

3) В кабинете ЮKassa укажи URL webhook:

```
https://<ngrok-domain>/yookassa/webhook
```

И включи Basic Auth теми же логином/паролем, что в `.env` (`WEBHOOK_BASIC_USER`/`WEBHOOK_BASIC_PASS`).

## Файл после оплаты

Положи нужный файл в проект и укажи путь в `.env` как `SUBSCRIPTION_FILE`.

По умолчанию отправляется `subscription.txt`.
