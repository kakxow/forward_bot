import asyncio
import logging
import os
import sys
from typing import cast

import aiogram
import dotenv
from aiogram import Bot, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    PhotoSize,
    User,
)

from birthdays import add_birthday, congrats_today_birthdays, get_birthdays, is_valid
from db import create_tables, load_pic, save_pic

dotenv.load_dotenv()

CHAT_ID = int(os.environ["CHAT_ID"])
_raw_ids = os.environ["IMAGE_THREADS"]
IMAGE_THREAD_IDS = [int(x) for x in _raw_ids.split(",")]
COMMENT_THREAD_ID = int(os.environ["COMMENT_THREAD"])
DELETE_DELAY = float(os.environ["DELETE_DELAY"])
RULES_THREAD = os.environ["RULES_THREAD"]
GUIDE_THREAD = os.environ["GUIDE_THREAD"]
SURVEY_THREAD = os.environ["SURVEY_THREAD"]

allowed_entities = ("url", "text_link")
allowed_content = F.user.is_bot | F.photo | F.video | F.audio | F.document | F.animation

show_bdays_cmd = "show_bdays"
welcome_pic_command = "welcome_pic"

add_bday_success_id = "add_bday_success"
add_bday_fail_id = "add_bday_fail"

image_thread_reply = "{user_tag}, Ваш комментарий перенаправлен в {message_link}"
comment_thread_name = "Обсуждения"
comment_thread_author_reply = "Comment to your post forwarded here, {}"

add_bday_inline_title = "Add birthday"
add_bday_pending_msg = "Adding birthday..."
add_bday_fail_msg = "Date format is invalid. Try something like 25-07"
add_bday_error_msg = "Some error happened, try again later or contact maintainer."
add_bday_success_msg = "Birthday added - {}"
add_bday_button_txt = "Add your birthday too!"

welcome_message = """Ну здравствуй, {}!

Добро пожаловать в наше <tg-spoiler>греховное</tg-spoiler> уютное сообщество. Всем уже не терпится с тобой познакомиться! Заполняй анкету, просмотри правила и, конечно же, устраивайся поудобнее 🫦 

PS. Заполнение анкеты носит исключительно ознакомительный характер, ролевить насильно никого мы не заставляем."""
rules_button_caption = "Правила"
guide_button_caption = "Путеводитель"
survey_button_caption = "Анкета"


class WelcomePic(StatesGroup):
    """FSM for updating welcome picture."""

    query_pic = State()
    got_pic = State()


add_bday_inline_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text=add_bday_button_txt,
                switch_inline_query_current_chat="",
            ),
        ],
    ],
)

tasks = []

dp = aiogram.Dispatcher()


async def del_msg(message: Message) -> None:
    """Delete message after delay."""
    await asyncio.sleep(DELETE_DELAY)
    await message.delete()


def user_link(user: User) -> str:
    """Generate telegram-valid html link for user."""
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'


def message_link(message_id: int, text: str, chat_id: int = CHAT_ID) -> str:
    """Generate telegram-valid html link for message/topic."""
    encoded_chat_id = abs(chat_id) % 10**12
    message_link = f"{encoded_chat_id}/{message_id}"
    return f'<a href="https://t.me/c/{message_link}">{text}</a>'


@dp.message(
    (F.chat.id == CHAT_ID)
    & (F.message_thread_id.in_(IMAGE_THREAD_IDS))
    & ~allowed_content,
)
async def forward(comment: Message) -> None:
    """Forward messages from image thread to comment thread."""
    entities = comment.entities
    if entities and any((e.type in allowed_entities) for e in entities):
        return
    original_message = comment.reply_to_message
    # If message is a reply to somethign - forward original message too and mention author.
    if original_message and original_message.message_id not in IMAGE_THREAD_IDS:
        try:
            forwarded_original = await original_message.forward(
                comment.chat.id,
                COMMENT_THREAD_ID,
            )
        except TelegramBadRequest:
            forwarded_original = await original_message.copy_to(
                comment.chat.id,
                COMMENT_THREAD_ID,
            )
        forwarded_original_id = forwarded_original.message_id
        # We're not in a channel, so we'll always have a User here.
        original_user = cast("User", original_message.from_user)
        original_user_link = user_link(original_user)
        await aiogram.methods.send_message.SendMessage(
            chat_id=comment.chat.id,
            text=comment_thread_author_reply.format(original_user_link),
            reply_to_message_id=forwarded_original_id,
        )
    # Forward comment and delete it.
    forwarded_comment = await comment.forward(comment.chat.id, COMMENT_THREAD_ID)
    await comment.delete()

    # We're not in a channel, so we'll always have a User here.
    comment_user = cast("User", comment.from_user)

    comment_user_link = user_link(comment_user)
    msg_link = message_link(forwarded_comment.message_id, comment_thread_name)
    answer = await comment.answer(
        image_thread_reply.format(user_tag=comment_user_link, message_link=msg_link),
    )
    f = asyncio.Task(del_msg(answer))
    tasks.append(f)


@dp.message(Command(show_bdays_cmd))
async def show_bdays(message: Message) -> None:
    """Show all birthdays."""
    msg = await get_birthdays(message.chat.id)
    await message.answer(msg)


@dp.chosen_inline_result()
async def add_bday(res: ChosenInlineResult) -> None:
    """Add birthday from inline result."""
    bot = cast("Bot", res.bot)

    if res.result_id != add_bday_success_id:
        return
    # We should have this by design in bday function.
    if not res.inline_message_id:
        raise RuntimeError
    try:
        await add_birthday(res.from_user, CHAT_ID, res.query.strip())
    except Exception:
        await bot.edit_message_text(
            text=add_bday_error_msg,
            inline_message_id=res.inline_message_id,
        )
        raise
    else:
        await bot.edit_message_text(
            text=add_bday_success_msg.format(res.query.strip()),
            inline_message_id=res.inline_message_id,
        )


@dp.inline_query()
async def bday(inline_query: InlineQuery) -> None:
    """Respond to inline queries for adding bdays."""
    msg_success = InputTextMessageContent(message_text=add_bday_pending_msg)
    response_success = InlineQueryResultArticle(
        id=add_bday_success_id,
        title=add_bday_inline_title,
        input_message_content=msg_success,
        reply_markup=add_bday_inline_markup,
    )

    query = inline_query.query.strip()
    if is_valid(query):
        await inline_query.answer([response_success], cache_time=0)
    else:
        await inline_query.answer([], cache_time=0)


@dp.message(F.new_chat_members & (F.chat.id == CHAT_ID))
async def welcome_post(message: Message) -> None:
    """Make a welcome post on member joined."""
    pic = await load_pic()
    new_chat_members = cast("list[User]", message.new_chat_members)
    user = new_chat_members[0]

    welcome_msg = welcome_message.format(user_link(user))
    chat_id = abs(CHAT_ID) % 10**12
    chat_link = f"https://t.me/c/{chat_id}"
    welcome_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=rules_button_caption,
                    url=f"{chat_link}/{RULES_THREAD}",
                ),
                InlineKeyboardButton(
                    text=guide_button_caption,
                    url=f"{chat_link}/{GUIDE_THREAD}",
                ),
                InlineKeyboardButton(
                    text=survey_button_caption,
                    url=f"{chat_link}/{SURVEY_THREAD}",
                ),
            ],
        ],
    )
    # If no pic - send welcome message anyway.
    if not pic:
        await message.answer(text=welcome_msg, reply_markup=welcome_kb)
    else:
        await message.answer_photo(
            photo=pic,
            caption=welcome_msg,
            reply_markup=welcome_kb,
        )


@dp.message(Command(welcome_pic_command), F.chat.type == ChatType.PRIVATE)
async def start_welcome_pic_query(message: Message, state: FSMContext) -> None:
    """Request picture for welcome message from the user."""
    # We're not in a channel, nothing to worry about here.
    user = cast("User", message.from_user)
    bot = cast("Bot", message.bot)

    # Authorizing user:
    admins = await bot.get_chat_administrators(CHAT_ID)
    admins_id = [admin.user.id for admin in admins]
    if user.id not in admins_id:
        await message.answer("You're not authorized to change welcome photo.")
        return

    await state.set_state(WelcomePic.query_pic)
    await message.answer("Please send exactly one photo.")


@dp.message(WelcomePic.query_pic, F.photo)
async def set_welcome_pic(message: Message, state: FSMContext) -> None:
    """Set welcome pic as we got one successfully."""
    await state.set_state(WelcomePic.got_pic)
    # We already have a photo because of the filtering.
    photo = cast("list[PhotoSize]", message.photo)

    pic = photo[0].file_id
    await save_pic(pic)
    await state.clear()
    await message.answer("New welcome picture added.")


@dp.message(WelcomePic.query_pic)
async def getting_pic(message: Message, state: FSMContext) -> None:  # noqa: ARG001
    """Reply to non-valid response to picture query."""
    await message.answer("You did not send a photo, please send a photo.")


async def main() -> None:
    """Create bot, tables, check bdays and start a bot."""
    bot = aiogram.Bot(
        token=os.getenv("BOT_TOKEN", ""),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )
    await create_tables()
    await congrats_today_birthdays(bot)
    await dp.start_polling(
        bot,
        polling_timeout=30,
        handle_as_tasks=True,
        tasks_concurrency_limit=10,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
