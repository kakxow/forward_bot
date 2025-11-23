import datetime as dt
import re
from itertools import groupby

import aiogram
from aiogram.enums import ChatMemberStatus
from aiogram.types import (
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberOwner,
    ChatMemberRestricted,
)

from db import fetch_birthday_ppl, fetch_users_with_bdays, update_user

type ChatMembers = (
    ChatMemberOwner
    | ChatMemberAdministrator
    | ChatMemberMember
    | ChatMemberRestricted
    | ChatMemberLeft
    | ChatMemberBanned
)


async def get_birthdays(chat_id: int) -> str:
    """Get all birthdays for given chat id, sort and prepare for posting to a chat."""
    users_with_bdays = await fetch_users_with_bdays(chat_id)

    text_birthdays = [f"•{user.first_name} {user.username}: {user.birthday:%d.%m}" for user in users_with_bdays]
    text = "<b>Birthday calendar</b>\n"
    birthday_table = "\n".join(text_birthdays) or "Nothing to show yet!"
    return text + birthday_table


async def congrats_today_birthdays(bot: aiogram.Bot) -> None:
    """Send bdays congrats for today."""
    birthday_ppl = await fetch_birthday_ppl()
    for chat_id, group in groupby(birthday_ppl, lambda el: el[0]):
        chat_members: list[ChatMembers] = []
        for _, user_id in group:
            chat_member = await bot.get_chat_member(chat_id, user_id)

            if chat_member.status != ChatMemberStatus.LEFT:
                chat_members.append(chat_member)
        if not chat_members:
            continue

        usernames = [
            f'<a href="tg://user?id={chat_member.user.id}">{chat_member.user.first_name}</a>'
            for chat_member in chat_members
        ]

        mentions = ", ".join(usernames)
        await bot.send_message(chat_id, f"Happy birthday {mentions}!")


async def add_birthday(user: aiogram.types.User, chat_id: int, birthday: str) -> None:
    """Extract birthday from a string and update user with their new bday date."""
    bday = extract_bday(birthday)
    await update_user(chat_id, user, {"birthday": bday})


def extract_bday(birthday: str) -> dt.date:
    """Extract bday from a string in the form of [day][separator][month]."""
    m = re.match(r"(?P<day>\d{2}).(?P<month>\d{2})", birthday)
    if not m:
        raise ValueError
    day, month = m.groups()
    # 2000 for leap years
    return dt.datetime(2000, int(month), int(day))  # noqa: DTZ001


def is_valid(birthday: str) -> bool:
    """Return True if it's possible to extract valid date from a string."""
    try:
        extract_bday(birthday)
    except ValueError:
        return False
    return True
