from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: str
    telegram_user_id: int
    status: str
    created_at: Optional[str] = None


class Storage:
    def __init__(self, db_path: str | Path = "bot.db") -> None:
        self._db_path = str(db_path)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    email TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    telegram_user_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def set_user_email(self, telegram_user_id: int, email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(telegram_user_id, email)
                VALUES(?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET email=excluded.email;
                """,
                (telegram_user_id, email),
            )

    def get_user_email(self, telegram_user_id: int) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email FROM users WHERE telegram_user_id=?",
                (telegram_user_id,),
            ).fetchone()
            return str(row["email"]) if row else None

    def upsert_payment(self, payment_id: str, telegram_user_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO payments(payment_id, telegram_user_id, status)
                VALUES(?, ?, ?)
                ON CONFLICT(payment_id) DO UPDATE SET status=excluded.status;
                """,
                (payment_id, telegram_user_id, status),
            )

    def get_payment(self, payment_id: str) -> Optional[PaymentRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payment_id, telegram_user_id, status, created_at FROM payments WHERE payment_id=?",
                (payment_id,),
            ).fetchone()
            if not row:
                return None
            return PaymentRecord(
                payment_id=str(row["payment_id"]),
                telegram_user_id=int(row["telegram_user_id"]),
                status=str(row["status"]),
                created_at=str(row["created_at"]) if row["created_at"] else None,
            )
