import asyncio
import os

import uvicorn
from dotenv import load_dotenv

from api_app import app
from bot_app import dp, bot
from db import init_db

load_dotenv()

SQLITE_PATH = os.environ.get("SQLITE_PATH", "app.db")


@app.on_event("startup")
async def _startup() -> None:
    init_db(SQLITE_PATH)
    asyncio.create_task(dp.start_polling(bot))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
