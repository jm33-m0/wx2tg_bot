#!/usr/bin/python3

'''
this script forwards your wechat messages to telegram,
you can also send reply to each message
'''

# pylint: disable=unused-argument,broad-except

import logging
import traceback
import sys

import wxpy

import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

LOGGER = logging.getLogger(__name__)

# init
TGKEY = 0
CHAT_ID = 0
MSGS = {}

# read config file
try:
    with open('bot.conf') as conf:
        for line in conf:
            line = line.strip()
            value = line.split('=')[1]
            if line.startswith("chat_id"):
                CHAT_ID = value
                logging.debug("chatid: %s", str(CHAT_ID))
            elif line.startswith("tgbot"):
                TGKEY = value
                logging.debug("tgkey: %s", str(TGKEY))
            elif line.startswith("owner"):
                OWNER_ID = int(value)
except FileNotFoundError:
    logging.error("can't find bot.conf")
except BaseException:
    logging.warning(traceback.format_exc())
    logging.error("can't read bot.conf")
    sys.exit(1)

# start wechat login and define telegram bot
TGBOT = telegram.Bot(TGKEY)
BOT = wxpy.Bot(console_qr=True)


# how wechat bot should behave
@BOT.register()
def get_message(msg):
    '''
    get new wechat msg and deal with it
    '''

    # ignore group messages
    if isinstance(msg.chat, wxpy.Group) and not msg.is_at:
        return

    # remember the messages received, in case i want to reply later
    tg_message = TGBOT.send_message(CHAT_ID, str(msg))
    MSGS.update({tg_message: msg})

    # fwd everything to telegram
    if msg.type == wxpy.ATTACHMENT:
        logging.info("get file")
        filename_origin = msg.file_name
        # in case telegram cant parse zh_CN file names
        file_to_send = "file." + filename_origin.split('.')[-1]

        msg.get_file(save_path="./wxfiles/{}".format(file_to_send))
        logging.info("downloaded")
        TGBOT.send_message(CHAT_ID, str(msg) + " :\n" + filename_origin)
        try:
            TGBOT.send_document(CHAT_ID, open(
                "./wxfiles/{}".format(file_to_send), "rb"), filename=filename_origin)
        except BaseException:
            logging.warning(traceback.format_exc())
            TGBOT.send_document(CHAT_ID, open(
                "./wxfiles/{}".format(file_to_send), "rb"), filename=file_to_send)
            return
        logging.info("sent")
    elif msg.type == wxpy.RECORDING:
        logging.info("get voice")
        msg.get_file(save_path="./wxfiles/voice")
        logging.info("downloaded")
        try:
            TGBOT.send_voice(CHAT_ID, open(
                "./wxfiles/voice", "rb"))
        except BaseException:
            logging.warning(traceback.format_exc())
            return
        logging.info("sent")
    elif msg.type == wxpy.PICTURE:
        logging.info("get img")
        msg.get_file(save_path="./wxfiles/img")
        logging.info("downloaded")
        try:
            TGBOT.send_photo(CHAT_ID, open(
                "./wxfiles/img", "rb"))
        except BaseException:
            logging.warning(traceback.format_exc())
            return
        logging.info("sent")
    elif msg.type == wxpy.VIDEO:
        logging.info("got video")
        msg.get_file(save_path="./wxfiles/video")
        logging.info("downloaded")
        try:
            TGBOT.send_video(CHAT_ID, open(
                "./wxfiles/video", "rb"))
        except BaseException:
            logging.warning(traceback.format_exc())
            return
        logging.info("sent")


# start telegram bot

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.


def start(bot, update):
    """Send a message when the command /start is issued."""
    update.message.reply_text(
        'I am your WeChat bot, I handle your fucking WeChat')

    chat_id = update.message.chat.id
    owner_id = update.message.from_user.id

    # check if `chat` conf exists
    with open("bot.conf") as confread:
        for item in confread:
            item = item.strip()
            if item.startswith("chat"):
                confread.close()
                return
            logging.debug("command /start reading: %s", item)
        confread.close()

    # write `chat` conf
    botconf = open('bot.conf', 'a+')
    botconf.write("chat_id={}\n".format(chat_id))
    botconf.write("owner={}\n".format(owner_id))
    botconf.close()


def reply_photo_to_wechat(bot, update):
    """find which message I am replying to, and send message to coresponding wechat receivers"""
    try:
        reply_msg = update.message.reply_to_message

        # save the photo so that it can be sent to wechat
        update.message.photo[-1].get_file().download(
            custom_path="./tgfiles/pic")

        wx_msg = MSGS.get(reply_msg)
        wx_msg.reply_image("./tgfiles/pic")
    except BaseException:
        logging.warning(traceback.format_exc())
        logging.error(
            "failed sending photo to wechat, sending to filehelper instead")
        BOT.file_helper.send_image("./tgfiles/pic")


def reply_file_to_wechat(bot, update):
    """find which message I am replying to, and send message to coresponding wechat receivers"""
    try:
        reply_msg = update.message.reply_to_message

        # save the photo so that it can be sent to wechat
        file_name = update.message.document.file_name
        update.message.document.get_file().download(
            custom_path="./tgfiles/{}".format(file_name))

        wx_msg = MSGS.get(reply_msg)
        wx_msg.reply_file("./tgfiles/{}".format(file_name))
    except BaseException:
        logging.warning(traceback.format_exc())
        logging.error(
            "failed sending file to wechat, sending it to filehelper instead")

        try:
            BOT.file_helper.send_file("./tgfiles/{}".format(file_name))
        except BaseException:
            # transfer.sh is our last resort
            import requests
            files = {'upload_file': open("./tgfiles/"+file_name, 'rb')}
            resp = requests.put(
                "https://transfer.sh/{}".format(file_name), files=files, verify=False)
            download_url = resp.text
            wx_msg.reply(download_url)


def reply_to_wechat(bot, update):
    """find which message I am replying to, and send message to coresponding wechat receivers"""
    try:
        # normal response
        reply_msg = update.message.reply_to_message

        msg_to_send = update.message.text

        # record everything
        record(update)

        chatid = update.message.chat.id
        msgid = update.message.message_id
        userid = update.message.from_user.id

        # fuck strangers
        if userid != OWNER_ID:
            msg_to_send = str(update.message.from_user) + \
                '\n' + str(update.message.chat) + '\n\n' + update.message.text

            # try to remove members
            try:
                logging.info(TGBOT.get_chat_administrators(chatid))
                TGBOT.delete_message(chatid, msgid)
                TGBOT.kick_chat_member(chatid, userid)
            except BaseException:
                logging.error(traceback.format_exc())

            # send shit pics to strangers
            for index in range(0, 6):
                try:
                    TGBOT.send_photo(chatid,
                                     open("./tgfiles/shit{}.jpg".format(index), "rb"))
                except BaseException:
                    logging.warning("shit pics not found")

            # send final words
            try:
                TGBOT.send_message(chatid, "Sorry but I don't like strangers")
            except BaseException:
                logging.warning("can't send final words")

            return

        # send to wechat user
        wx_msg = MSGS.get(reply_msg)
        wx_msg.reply(msg_to_send)
    except BaseException:
        logging.error(
            "failed sending reply to wechat, sending to filehelper instead")
        BOT.file_helper.send_msg(msg_to_send)


def record(update):
    """
    get info about the chat
    """
    logging.info(update.message.from_user)
    logging.info(update.message.chat)


def error(bot, update, err):
    """Log Errors caused by Updates."""
    LOGGER.warning('Update "%s" caused error "%s"', update, err)


def start_tgbot():
    """Start the bot."""
    # Create the EventHandler and pass it your bot's token.
    updater = Updater(TGKEY)

    # Get the dispatcher to register handlers
    wx2tg_dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    wx2tg_dispatcher.add_handler(CommandHandler("start", start))

    # on noncommand i.e message - echo the message on Telegram
    wx2tg_dispatcher.add_handler(MessageHandler(Filters.text, reply_to_wechat))
    wx2tg_dispatcher.add_handler(MessageHandler(
        Filters.document, reply_file_to_wechat))
    wx2tg_dispatcher.add_handler(MessageHandler(
        Filters.photo, reply_photo_to_wechat))

    # log all errors
    wx2tg_dispatcher.add_error_handler(error)

    # Start the Bot
    updater.start_polling()


if __name__ == "__main__":
    try:
        # start telegram bot
        start_tgbot()

        # start WeChat bot on main thread
        BOT.join()
    except BaseException:
        logging.error(traceback.format_exc())
