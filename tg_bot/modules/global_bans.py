import html
from io import BytesIO
from typing import Optional, List

from telegram import Message, Update, Bot, User, Chat, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import run_async, CommandHandler, MessageHandler, Filters
from telegram.utils.helpers import mention_html

import tg_bot.modules.sql.global_bans_sql as sql
from tg_bot import dispatcher, OWNER_ID, SUDO_USERS, SUPPORT_USERS, STRICT_GBAN
from tg_bot.modules.helper_funcs.chat_status import user_admin, is_user_admin
from tg_bot.modules.helper_funcs.extraction import extract_user, extract_user_and_text
from tg_bot.modules.helper_funcs.filters import CustomFilters
from tg_bot.modules.helper_funcs.misc import send_to_list
from tg_bot.modules.sql.users_sql import get_all_chats

GBAN_ENFORCE_GROUP = 6

GBAN_ERRORS = {
    "Kullanıcı sohbetin yöneticisidir",
    "Sohbet bulunamadı",
    "Sohbet üyesini kısıtlamak / kısıtlamak için yeterli hak yok",
    "User_not_participant",
    "Peer_id_invalid",
    "Grup sohbeti devre dışı bırakıldı",
    "Basit bir gruptan atmak için bir kullanıcının davetlisi olması gerekir",
    "Chat_admin_required",
    "Yalnızca temel bir grubu oluşturan kişi grup yöneticilerini atabilir",
    "Channel_private",
    "Sohbette değil"
}

UNGBAN_ERRORS = {
    "Kullanıcı sohbetin yöneticisidir",
    "Sohbet bulunamadı",
    "Sohbet üyesini kısıtlamak / kısıtlamak için yeterli hak yok",
    "User_not_participant",
    "Yöntem yalnızca süper grup ve kanal sohbetleri için kullanılabilir",
    "Sohbette değil",
    "Channel_private",
    "Chat_admin_required",
}


@run_async
def gban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message]

    user_id, reason = extract_user_and_text(message, args)

    if not user_id:
        message.reply_text("Bir kullanıcıya atıfta bulunmuyorsunuz.")
        return

    if int(user_id) in SUDO_USERS:
        message.reply_text("Küçük gözümle casusluk yapıyorum... bir sudo kullanıcı savaşı! Neden birbirinize düşman oluyorsunuz?")
        return

    if int(user_id) in SUPPORT_USERS:
        message.reply_text("OOOH birisi bir destek kullanıcısını gban etmeye çalışıyor! *patlamış mısır kapar*")
        return

    if user_id == bot.id:
        message.reply_text("-_- Çok komik, kendimi gban, neden yapmayayım? İyi deneme.")
        return

    try:
        user_chat = bot.get_chat(user_id)
    except BadRequest as excp:
        message.reply_text(excp.message)
        return

    if user_chat.type != 'private':
        message.reply_text("Bu bir kullanıcı değil!")
        return

    if sql.is_user_gbanned(user_id):
        if not reason:
            message.reply_text("Bu kullanıcı zaten yasaklanmış; Sebebini değiştirirdim, ama bana bir tane vermedin...")
            return

        old_reason = sql.update_gban_reason(user_id, user_chat.username or user_chat.first_name, reason)
        if old_reason:
            message.reply_text("Bu kullanıcı, aşağıdaki nedenden dolayı zaten yasaklandı:\n"
                               "<code>{}</code>\n"
                               "Gittim ve yeni sebebinizle güncelledim!".format(html.escape(old_reason)),
                               parse_mode=ParseMode.HTML)
        else:
            message.reply_text("Bu kullanıcı zaten yasaklanmış, ancak herhangi bir nedeni belirlenmemiş; Gittim ve güncelledim!")

        return

    message.reply_text("⚡️ *Banhammer'ı Yakalar* ⚡️")

    banner = update.effective_user  # type: Optional[User]
    send_to_list(bot, SUDO_USERS + SUPPORT_USERS,
                 "<b>Global Ban</b>" \
                 "\n#GBAN" \
                 "\n<b>Durum:</b> <code>Zorlama</code>" \
                 "\n<b>Sudo Admin:</b> {}" \
                 "\n<b>Kullanıcı:</b> {}" \
                 "\n<b>ID:</b> <code>{}</code>" \
                 "\n<b>Nedeni:</b> {}".format(mention_html(banner.id, banner.first_name),
                                              mention_html(user_chat.id, user_chat.first_name), 
                                                           user_chat.id, reason or "Sebep yok"), 
                html=True)

    sql.gban_user(user_id, user_chat.username or user_chat.first_name, reason)

    chats = get_all_chats()
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            bot.kick_chat_member(chat_id, user_id)
        except BadRequest as excp:
            if excp.message in GBAN_ERRORS:
                pass
            else:
                message.reply_text("{} Nedeniyle gban yapılamadı".format(excp.message))
                send_to_list(bot, SUDO_USERS + SUPPORT_USERS, "{} Nedeniyle gban yapılamadı".format(excp.message))
                sql.ungban_user(user_id)
                return
        except TelegramError:
            pass

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS, 
                  "{} başarıyla yasaklandı!".format(mention_html(user_chat.id, user_chat.first_name)),
                html=True)
    message.reply_text("Kişi yasaklandı.")


@run_async
def ungban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message]

    user_id = extract_user(message, args)
    if not user_id:
        message.reply_text("Bir kullanıcıya atıfta bulunmuyorsunuz.")
        return

    user_chat = bot.get_chat(user_id)
    if user_chat.type != 'private':
        message.reply_text("Bu bir kullanıcı değil!")
        return

    if not sql.is_user_gbanned(user_id):
        message.reply_text("Bu kullanıcı yasaklanmadı!")
        return

    banner = update.effective_user  # type: Optional[User]

    message.reply_text("Dünya çapında ikinci bir şansla {} için özür dilerim.".format(user_chat.first_name))

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS,
                 "<b>Regression of Global Ban</b>" \
                 "\n#UNGBAN" \
                 "\n<b>Durum:</b> <code>Durduruldu</code>" \
                 "\n<b>Sudo Admin:</b> {}" \
                 "\n<b>Kullanıcı:</b> {}" \
                 "\n<b>ID:</b> <code>{}</code>".format(mention_html(banner.id, banner.first_name),
                                                       mention_html(user_chat.id, user_chat.first_name), 
                                                                    user_chat.id),
                 html=True)

    chats = get_all_chats()
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status == 'kicked':
                bot.unban_chat_member(chat_id, user_id)

        except BadRequest as excp:
            if excp.message in UNGBAN_ERRORS:
                pass
            else:
                message.reply_text("{} Nedeniyle gban kaldırılamadı".format(excp.message))
                bot.send_message(OWNER_ID, "{} Nedeniyle gban kaldırılamadı".format(excp.message))
                return
        except TelegramError:
            pass

    sql.ungban_user(user_id)

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS, 
                  "{} gban'dan affedildi!".format(mention_html(user_chat.id, 
                                                                         user_chat.first_name)),
                  html=True)

    message.reply_text("Bu kişinin yasağı kaldırıldı ve affedildi!")


@run_async
def gbanlist(bot: Bot, update: Update):
    banned_users = sql.get_gban_list()

    if not banned_users:
        update.effective_message.reply_text("Yasaklı kullanıcı yok! Beklediğimden daha naziksin ...")
        return

    banfile = 'Bu adamları boşver.\n'
    for user in banned_users:
        banfile += "[x] {} - {}\n".format(user["name"], user["user_id"])
        if user["reason"]:
            banfile += "Nedeni: {}\n".format(user["reason"])

    with BytesIO(str.encode(banfile)) as output:
        output.name = "gbanlist.txt"
        update.effective_message.reply_document(document=output, filename="gbanlist.txt",
                                                caption="İşte şu anda yasaklanmış kullanıcıların listesi.")


def check_and_ban(update, user_id, should_message=True):
    if sql.is_user_gbanned(user_id):
        update.effective_chat.kick_member(user_id)
        if should_message:
            update.effective_message.reply_text("Bu kötü bir insan, burada olmamalılar!")


@run_async
def enforce_gban(bot: Bot, update: Update):
    # Not using @restrict handler to avoid spamming - just ignore if cant gban.
    if sql.does_chat_gban(update.effective_chat.id) and update.effective_chat.get_member(bot.id).can_restrict_members:
        user = update.effective_user  # type: Optional[User]
        chat = update.effective_chat  # type: Optional[Chat]
        msg = update.effective_message  # type: Optional[Message]

        if user and not is_user_admin(chat, user.id):
            check_and_ban(update, user.id)

        if msg.new_chat_members:
            new_members = update.effective_message.new_chat_members
            for mem in new_members:
                check_and_ban(update, mem.id)

        if msg.reply_to_message:
            user = msg.reply_to_message.from_user  # type: Optional[User]
            if user and not is_user_admin(chat, user.id):
                check_and_ban(update, user.id, should_message=False)


@run_async
@user_admin
def gbanstat(bot: Bot, update: Update, args: List[str]):
    if len(args) > 0:
        if args[0].lower() in ["on", "yes"]:
            sql.enable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Bu grupta gbans etkinleştirdim. Bu seni korumaya yardımcı olacak "
                                                "spam gönderenlerden, tatsız karakterlerden ve en büyük trollerden.")
        elif args[0].lower() in ["off", "no"]:
            sql.disable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Bu grupta gbans'ı devre dışı bıraktım. GBan'lar kullanıcılarınızı etkilemeyecek "
                                                "artık. Trollerden ve spam gönderenlerden daha az korunacaksınız "
                                                "rağmen!")
    else:
        update.effective_message.reply_text("Bir ayar seçmek için bana bazı argümanlar verin! on/off, yes/no!\n\n"
                                            "Mevcut ayarınız: {}\n"
                                            "True olduğunda, gerçekleşen herhangi bir gbans da grubunuzda gerçekleşecek. "
                                            "Yanlış olduğunda, seni olası merhametine bırakmayacaklar "
                                            "spam gönderenler.".format(sql.does_chat_gban(update.effective_chat.id)))


def __stats__():
    return "{} engellenmiş kullanıcı.".format(sql.num_gbanned_users())


def __user_info__(user_id):
    is_gbanned = sql.is_user_gbanned(user_id)

    text = "Genel olarak yasaklandı: <b>{}</b>"
    if is_gbanned:
        text = text.format("Yes")
        user = sql.get_gbanned_user(user_id)
        if user.reason:
            text += "\n Gerekçe: {}".format(html.escape(user.reason))
    else:
        text = text.format("No")
    return text


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    return "Bu sohbet de *gbanlar*: `{}` uygulanıyor.".format(sql.does_chat_gban(chat_id))


__help__ = """
*Yalnızca yönetici:*
 - /gbanstat <on/off/yes/no>: `Global yasaklamaların grubunuz üzerindeki etkisini devre dışı bırakır veya mevcut ayarlarınıza döner.`

`Küresel yasaklar olarak da bilinen Gbans, bot sahipleri tarafından spam gönderenleri tüm gruplarda yasaklamak için kullanılır. Bu korumaya yardımcı olur \
spam sel baskınlarını olabildiğince çabuk kaldırarak siz ve gruplarınız. Arayarak grubunuz için devre dışı bırakılabilirler` \
`/gbanstat`
"""

__mod_name__ = "Global Bans"

GBAN_HANDLER = CommandHandler("gban", gban, pass_args=True,
                              filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
UNGBAN_HANDLER = CommandHandler("ungban", ungban, pass_args=True,
                                filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
GBAN_LIST = CommandHandler("gbanlist", gbanlist,
                           filters=CustomFilters.sudo_filter | CustomFilters.support_filter)

GBAN_STATUS = CommandHandler("gbanstat", gbanstat, pass_args=True, filters=Filters.group)

GBAN_ENFORCER = MessageHandler(Filters.all & Filters.group, enforce_gban)

dispatcher.add_handler(GBAN_HANDLER)
dispatcher.add_handler(UNGBAN_HANDLER)
dispatcher.add_handler(GBAN_LIST)
dispatcher.add_handler(GBAN_STATUS)

if STRICT_GBAN:  # enforce GBANS if this is set
    dispatcher.add_handler(GBAN_ENFORCER, GBAN_ENFORCE_GROUP)
