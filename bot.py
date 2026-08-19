import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split(",") if x.strip()]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- MA'LUMOTLAR BAZASI ---
conn = sqlite3.connect("kino_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute(
    "CREATE TABLE IF NOT EXISTS movies (code INTEGER PRIMARY KEY, file_id TEXT NOT NULL, caption TEXT)"
)
cursor.execute(
    "CREATE INDEX IF NOT EXISTS idx_caption ON movies(caption)"
)
cursor.execute(
    "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)"
)
cursor.execute(
    "CREATE TABLE IF NOT EXISTS channels (chat_id TEXT PRIMARY KEY, title TEXT, link TEXT)"
)
conn.commit()


# --- STATES ---
class AddMovieState(StatesGroup):
    waiting_for_video = State()
    waiting_for_caption = State()


class AddChannelState(StatesGroup):
    waiting_for_channel_info = State()


class DeleteMovieState(StatesGroup):
    waiting_for_code = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


# --- TUGMALAR ---
def get_user_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✨ Film izlash 🎬"),
                KeyboardButton(text="🎲 Kutilmagan film 🍿"),
            ],
            [
                KeyboardButton(text="⚙️ Admin Panel"),
                KeyboardButton(text="📊 Qiziqarli raqamlar 📈"),
            ],
            [
                KeyboardButton(text="🕊 Dil izhori / Yordam 💌"),
            ],
        ],
        resize_keyboard=True,
    )


def get_admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Kino qo'shish 🍿", callback_data="add_movie_btn"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Xushxabar yuborish 💌",
                    callback_data="admin_broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Maskandosh qo'shish 🌸",
                    callback_data="add_channel",
                ),
                InlineKeyboardButton(
                    text="❌ Kanalni uzish 🍃", callback_data="del_channel"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📜 Guvoh kanallar 🕊", callback_data="list_channels"
                ),
                InlineKeyboardButton(
                    text="🗑 Filmni yakunlash 🌙", callback_data="del_movie"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Umumiy holat 💎", callback_data="admin_stats"
                )
            ],
        ]
    )


def get_sub_keyboard(not_subscribed_channels: list):
    keyboard = [
        [InlineKeyboardButton(text=f"🌸 {title}", url=link)]
        for title, link in not_subscribed_channels
    ]
    keyboard.append(
        [
            InlineKeyboardButton(
                text="✅ Qadam qo'ydim / Tekshirish ✨",
                callback_data="check_sub",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_movie_inline_keyboard(bot_username: str, movie_code: int):
    share_link = f"https://t.me/share/url?url=https://t.me/{bot_username}?start={movie_code}&text=✨ Qalbingizga orom beruvchi ajoyib film topdim, siz ham ko'ring... 🎬🍿"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📲 Yaqinlarga ulashish 🕊", url=share_link
            )
        ],
        [
            InlineKeyboardButton(
                text="✨ Bizning maskan 🌙", url=f"https://t.me/{bot_username}"
            )
        ],
    ])


def get_next_movie_code() -> int:
    cursor.execute("SELECT MAX(code) FROM movies")
    result = cursor.fetchone()[0]
    return (result + 1) if result else 100


async def check_user_subscriptions(user_id: int) -> list:
    cursor.execute("SELECT chat_id, title, link FROM channels")
    channels = cursor.fetchall()
    not_subscribed = []
    for chat_id, title, link in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=chat_id, user_id=user_id
            )
            if member.status in [
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED,
            ]:
                not_subscribed.append((title, link))
        except Exception:
            pass
    return not_subscribed


# --- HANDLERLAR ---


@dp.message(CommandStart())
async def start_handler(message: types.Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (message.from_user.id,),
    )
    conn.commit()

    unsubbed = await check_user_subscriptions(message.from_user.id)
    if unsubbed and message.from_user.id not in ADMINS:
        await message.answer(
            "🌸 *Asho'ra vaqtingiz xayrli bo'lsin!* \n\nSizni ushbu go'zal kanallarimizda kutmoqdamiz. Ziyoratingizdan so'ng xizmatingizda bo'lamiz ✨",
            reply_markup=get_sub_keyboard(unsubbed),
            parse_mode="Markdown",
        )
        return

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        code = int(args[1])
        cursor.execute(
            "SELECT file_id, caption FROM movies WHERE code = ?", (code,)
        )
        res = cursor.fetchone()
        if res:
            me = await bot.get_me()
            await message.answer_video(
                video=res[0],
                caption=res[1],
                reply_markup=get_movie_inline_keyboard(me.username, code),
            )
            return

    await message.answer(
        "Assalomu alaykum, aziz mehmongohim 🕊\n\nQalbingizga orom beruvchi, o'zingiz xush ko'rgan filmni tomosha qilish uchun uning **kodini** yoki **nomini** yuboring... 🎬✨",
        reply_markup=get_user_menu(),
        parse_mode="Markdown",
    )


@dp.message(F.text == "⚙️ Admin Panel")
@dp.message(Command("panel"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer(
            "⚙️ *Xush kelibsiz, aziz Bosh Boshqaruvchi!* 🌹\n\nBugun maskanimizda qanday o'zgarishlar qilamiz?",
            reply_markup=get_admin_menu(),
            parse_mode="Markdown",
        )
    else:
        await message.answer("❌ Bu bo'lim faqat adminlar uchun mo'ljallangan.")


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery):
    unsubbed = await check_user_subscriptions(call.from_user.id)
    if not unsubbed:
        await call.message.delete()
        await call.message.answer(
            "✨ *Tashrifingizdan mamnunmiz!* \n\nEshiklarimiz siz uchun ochiq, endi dilga yoqadigan kinoni tanlab tomosha qilishingiz mumkin... 🎬🍿",
            reply_markup=get_user_menu(),
            parse_mode="Markdown",
        )
    else:
        await call.answer(
            "🍃 Hali ba'zi go'zal maskanlarimizga qadam qo'ymadingiz...",
            show_alert=True,
        )


@dp.message(F.text == "✨ Film izlash 🎬")
async def menu_search(message: types.Message):
    await message.answer(
        "✨ Qalbingiz tusagan o'sha sevimli filmingiz **kodini** yoki **nomini** shu yerga yozib yuboring... 💭"
    )


@dp.message(F.text == "🎲 Kutilmagan film 🍿")
async def menu_random_movie(message: types.Message):
    cursor.execute(
        "SELECT code, file_id, caption FROM movies ORDER BY RANDOM() LIMIT 1"
    )
    res = cursor.fetchone()
    if res:
        code, file_id, caption = res
        me = await bot.get_me()
        await message.answer_video(
            video=file_id,
            caption=caption,
            reply_markup=get_movie_inline_keyboard(me.username, code),
        )
    else:
        await message.answer(
            "🍃 Hozircha bu mo'jazgina sandig'imiz bo'sh turibdi..."
        )


@dp.message(F.text == "📊 Qiziqarli raqamlar 📈")
async def menu_stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movies")
    m_cnt = cursor.fetchone()[0]

    await message.answer(
        f"💎 *Maskanimiz holati:* \n\n👥 Siz kabi dilga yaqin insonlar: `{u_cnt}` ta\n🎬 Yig'ilgan ko'ngilxushliklar: `{m_cnt}` ta 🍿",
        parse_mode="Markdown",
    )


@dp.message(F.text == "🕊 Dil izhori / Yordam 💌")
async def menu_help(message: types.Message):
    await message.answer(
        "💌 *Savol va istaklaringiz bo'lsa...*\n\nBosh beruvchi: @abu_movebot hamrohingiz bo'lishdan mamnun 🌸",
        parse_mode="Markdown",
    )


# --- KINO QO'SHISH ---


@dp.callback_query(F.data == "add_movie_btn", F.from_user.id.in_(ADMINS))
async def add_movie_button_click(
    call: types.CallbackQuery, state: FSMContext
):
    await call.message.answer(
        "🎬 *Yangi film qo'shish bosqichi boshlandi!* ✨\n\nIltimos, bazaga qo'shmoqchi bo'lgan **videongizni** yuboring...",
        parse_mode="Markdown",
    )
    await state.set_state(AddMovieState.waiting_for_video)


@dp.message(
    AddMovieState.waiting_for_video,
    F.video,
    F.from_user.id.in_(ADMINS),
)
async def process_video_from_button(
    message: types.Message, state: FSMContext
):
    auto_code = get_next_movie_code()
    file_id = message.video.file_id

    await state.update_data(auto_code=auto_code, file_id=file_id)
    await message.answer(
        f"✅ *Video qabul qilindi!* 🌸\n\n"
        f"🔑 Biriktirilgan maxsus raqam: `{auto_code}`\n\n"
        f"📝 Endi ushbu film uchun **nomi/tafsifini** yozib yuboring...",
        parse_mode="Markdown",
    )
    await state.set_state(AddMovieState.waiting_for_caption)


@dp.message(F.video, F.from_user.id.in_(ADMINS))
async def auto_movie_upload(message: types.Message, state: FSMContext):
    auto_code = get_next_movie_code()
    file_id = message.video.file_id

    await state.update_data(auto_code=auto_code, file_id=file_id)
    await message.answer(
        f"🎬 *Video qabul qilindi!* 🌸\n\n"
        f"🔑 Biriktirilgan maxsus raqam: `{auto_code}`\n\n"
        f"📝 Endi ushbu film uchun **shirin bir tafsif (nomi)** yozib yuboring...",
        parse_mode="Markdown",
    )
    await state.set_state(AddMovieState.waiting_for_caption)


@dp.message(AddMovieState.waiting_for_caption, F.from_user.id.in_(ADMINS))
async def process_movie_caption(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data["auto_code"]
    file_id = data["file_id"]
    caption = message.text

    me = await bot.get_me()
    full_caption = (
        f"🎬 *{caption}*\n\n🔑 Film kodi: `{code}`\n✨ Maskanimiz: @{me.username}"
    )

    cursor.execute(
        "INSERT INTO movies (code, file_id, caption) VALUES (?, ?, ?)",
        (code, file_id, full_caption),
    )
    conn.commit()

    await message.answer(
        f"🎉 *Yangi film saqlandi!* ✨\n\n🔑 Kodi: `{code}`\n📄 Tafsifi: {caption}",
        parse_mode="Markdown",
    )
    await state.clear()


# --- ADMIN PANEL BOSHQA TUGMALARI ---


@dp.callback_query(F.data == "admin_stats", F.from_user.id.in_(ADMINS))
async def admin_stats_show(call: types.CallbackQuery):
    cursor.execute("SELECT COUNT(*) FROM users")
    u_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movies")
    m_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM channels")
    c_cnt = cursor.fetchone()[0]

    await call.answer(
        f"📊 Statistika:\n👥 Obunachilar: {u_cnt} ta\n🎬 Kinolar: {m_cnt} ta\n📢 Kanallar: {c_cnt} ta",
        show_alert=True,
    )


@dp.callback_query(F.data == "add_channel", F.from_user.id.in_(ADMINS))
async def add_channel_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "📢 **Kanal qo'shish usuli:**\n\nUshbu formatda yuboring:\n`CHAT_ID | KANAL NOMI | HAVOLA`\n\nMasalan:\n`-100123456789 | Bosh Kanal | https://t.me/kanal_link`"
    )
    await state.set_state(AddChannelState.waiting_for_channel_info)


@dp.message(
    AddChannelState.waiting_for_channel_info, F.from_user.id.in_(ADMINS)
)
async def process_add_channel(message: types.Message, state: FSMContext):
    try:
        chat_id, title, link = map(str.strip, message.text.split("|"))
        cursor.execute(
            "INSERT INTO channels (chat_id, title, link) VALUES (?, ?, ?)",
            (chat_id, title, link),
        )
        conn.commit()
        await message.answer(f"✅ **{title}** kanali qo'shildi!")
    except Exception:
        await message.answer(
            "❌ Format xato! Namuna bo'yicha to'g'ri kiriting."
        )
    await state.clear()


@dp.callback_query(F.data == "list_channels", F.from_user.id.in_(ADMINS))
async def list_channels(call: types.CallbackQuery):
    cursor.execute("SELECT chat_id, title, link FROM channels")
    channels = cursor.fetchall()
    if not channels:
        await call.message.answer("📜 Majburiy obuna kanallari yo'q.")
        return

    text = "📜 **Ulangan kanallar:**\n\n"
    for cid, title, link in channels:
        text += f"🔹 **{title}**\nID: `{cid}`\nHavola: {link}\n\n"
    await call.message.answer(text)


@dp.callback_query(F.data == "del_movie", F.from_user.id.in_(ADMINS))
async def delete_movie_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "🗑 O'chirmoqchi bo'lgan kino **kodini** yuboring:"
    )
    await state.set_state(DeleteMovieState.waiting_for_code)


@dp.message(DeleteMovieState.waiting_for_code, F.from_user.id.in_(ADMINS))
async def process_delete_movie(message: types.Message, state: FSMContext):
    if message.text.isdigit():
        code = int(message.text)
        cursor.execute("DELETE FROM movies WHERE code = ?", (code,))
        conn.commit()
        await message.answer(f"✅ `{code}`-kodli kino o'chirildi!")
    else:
        await message.answer("❌ Faqat raqamlardan iborat kod yuboring.")
    await state.clear()


@dp.callback_query(F.data == "admin_broadcast", F.from_user.id.in_(ADMINS))
async def broadcast_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer(
        "📢 Barcha foydalanuvchilarga yuboriladigan xabar/reklamani yuboring:"
    )
    await state.set_state(BroadcastState.waiting_for_message)


@dp.message(BroadcastState.waiting_for_message, F.from_user.id.in_(ADMINS))
async def process_broadcast(message: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    count = 0
    await message.answer("🚀 Reklama tarqatish boshlandi...")

    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(
        f"✅ Reklama tarqatildi!\n👥 Yetib bordi: `{count}` ta foydalanuvchi."
    )
    await state.clear()


# --- KINO QIDIRISH (KOD YOKI NOM ORQALI) ---
@dp.message(F.text)
async def get_movie(message: types.Message):
    unsubbed = await check_user_subscriptions(message.from_user.id)
    if unsubbed and message.from_user.id not in ADMINS:
        await message.answer(
            "🌸 *Kichik bir iltimos...* \n\nUshbu go'zal kanallarimizga ulanib oling va filmni zavq bilan tomosha qiling ✨",
            reply_markup=get_sub_keyboard(unsubbed),
            parse_mode="Markdown",
        )
        return

    text = message.text.strip()
    me = await bot.get_me()

    # 1. Kod bo'yicha qidirish
    if text.isdigit():
        code = int(text)
        cursor.execute(
            "SELECT file_id, caption FROM movies WHERE code = ?", (code,)
        )
        res = cursor.fetchone()

        if res:
            file_id, caption = res
            await message.answer_video(
                video=file_id,
                caption=caption,
                reply_markup=get_movie_inline_keyboard(me.username, code),
            )
        else:
            await message.answer(
                "🍃 Afsuski, bunday raqamli film topilmadi..."
            )

    # 2. Nom bo'yicha qidirish
    else:
        cursor.execute(
            "SELECT code, file_id, caption FROM movies WHERE caption LIKE ? LIMIT 5",
            (f"%{text}%",),
        )
        results = cursor.fetchall()

        if results:
            for code, file_id, caption in results:
                await message.answer_video(
                    video=file_id,
                    caption=caption,
                    reply_markup=get_movie_inline_keyboard(
                        me.username, code
                    ),
                )
                await asyncio.sleep(0.3)
        else:
            await message.answer(
                "🍃 Afsuski, bunday nomli film topilmadi..."
            )


# --- RENDER UCHUN MINI WEB SERVER (bepul Web Service portni talab qiladi) ---
from aiohttp import web


async def handle_ping(request):
    return web.Response(text="Bot ishlayapti ✅")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


# --- MAIN ---
async def main():
    logging.basicConfig(level=logging.INFO)

    await bot.set_my_commands([
        types.BotCommand(
            command="start", description="🚀 Botni qayta ishga tushirish"
        ),
        types.BotCommand(
            command="panel", description="⚙️ Admin panel (Boshqaruv)"
        ),
    ])

    await start_web_server()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
