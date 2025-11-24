import asyncio
import os

import dotenv
from aiogram import Bot

from birthdays import congrats_today_birthdays

dotenv.load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]


async def main() -> None:
    bot = Bot(BOT_TOKEN)
    await congrats_today_birthdays(bot)


if __name__ == "__main__":
    asyncio.run(main())
