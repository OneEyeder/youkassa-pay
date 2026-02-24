import sqlite3
from typing import Optional


def init_db(sqlite_path: str) -> None:
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def create_payment_record(sqlite_path: str, payment_id: str, telegram_id: int, status: str, created_at: str) -> None:
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO payments(payment_id, telegram_id, status, created_at) VALUES (?, ?, ?, ?)",
            (payment_id, telegram_id, status, created_at),
        )
        conn.commit()


def get_payment(sqlite_path: str, payment_id: str) -> Optional[tuple[str, int, str, str]]:
    with sqlite3.connect(sqlite_path) as conn:
        cur = conn.execute(
            "SELECT payment_id, telegram_id, status, created_at FROM payments WHERE payment_id = ?",
            (payment_id,),
        )
        row = cur.fetchone()
        return row


def set_payment_status(sqlite_path: str, payment_id: str, status: str) -> None:
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "UPDATE payments SET status = ? WHERE payment_id = ?",
            (status, payment_id),
        )
        conn.commit()
