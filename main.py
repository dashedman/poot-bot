###############################################
#LIBS

import asyncio
import sqlite3
import time
import re
import argparse
import json
import sys
import os
import html
import ssl
import logging

from pprint import pprint, pformat
from collections import namedtuple, deque
from copy import deepcopy
from functools import partial
from random import randint

#ssl generate lib
from OpenSSL import crypto

#import requests
#asynchronious requests-like
from h11._util import RemoteProtocolError
from requests.exceptions import ConnectionError
import requests_async as requests

#asynchronious flask-like
from sanic import Sanic
from sanic.response import json as sanic_json

#streamlink lib
from streamlink import Streamlink, StreamError, PluginError, NoPluginError

#my local lib
from ui_constants import *


###############################################################
#
#  CONSTATNS
#
file_log = logging.FileHandler("botlogs.log", mode = "w")
console_out = logging.StreamHandler()
logging.basicConfig(
    handlers=(file_log, console_out),
    format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
    datefmt='%a %b %d %H:%M:%S %Y',
    level=logging.INFO)
BOTLOG = logging.getLogger("bot")


with open("config.ini","r") as f:
    BOT_NAME = f.readline()[:-1]
    TG_TOKEN = f.readline()[:-1]
    WEBHOOK_DOMEN = f.readline()[:-1]
    HOST_IP = f.readline()[:-1]



PORT = os.environ.get('PORT') or 443

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -1001483908315
WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}:{PORT}/{TG_TOKEN}/"

PKEY_FILE = "bot.pem"
KEY_FILE = "bot.key"
CERT_FILE = "bot.crt"
CERT_DIR = ""
SELF_SSL = True
ALIVE = True

STREAMERS = [
    {"platform":"wasd.tv", "name":"Mighty Poot (wasd)", "id":"mightypoot", "online": True},
    {"platform":"twitch.tv", "name":"Mighty Poot (twitch)", "id":"mightypoot", "online": True},
]

TG_CHANNELS = [
    -1001318931614
]

#StreamLink Session
SLS = Streamlink()
SLS.load_plugins("streamlink_plugins/")
SLS.set_plugin_option("twitch", "disable_hosting", True)
SLS.set_plugin_option("twitch", "disable_reruns", True)
SLS.set_plugin_option("twitch", "disable-ads", True)

############################################################
#
#FUNCTIONS
#
def create_self_signed_cert(cert_dir):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)   #  размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"   #  указываем свои данные
    cert.get_subject().ST = "Saint-Petersburg"
    cert.get_subject().L = "Saint-Petersburg"   #  указываем свои данные
    cert.get_subject().O = "musicforus"   #  указываем свои данные
    cert.get_subject().CN = WEBHOOK_DOMEN   #  указываем свои данные
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)   #  срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'SHA256')


    with open(os.path.join(cert_dir, CERT_FILE), "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii"))

    with open(os.path.join(cert_dir, KEY_FILE), "w") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("ascii"))

    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii")

#tg send functions
async def setWebhook(url='', certificate=None):
    await requests.post(
        TG_URL + 'setWebhook',
        data = {'url':url},
        files = {'certificate':certificate} if certificate else None,
        timeout=None
    )

async def getWebhookInfo():
    return await requests.post(TG_URL + 'getWebhookInfo', timeout=None)

async def sendMessage(chat_id, text, **kwargs):
    data = {
        'chat_id':chat_id,
        'text': text
    }
    data.update(kwargs)

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        pprint(r)
        if r['error_code'] == 429:
            await sendMessage(chat_id, f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after']+5} сек")
        else:
            raise Exception(f"bad Message: {r}")
    return r['result']

async def sendKeyboard(chat_id, text, keyboard, **kwargs):
    data = {
        'chat_id':chat_id,
        'text': text,
        'reply_markup': keyboard
    }
    data.update(kwargs)

    response = await requests.post(TG_URL + 'sendMessage', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        BOTLOG.info(pformat(r))
        pprint(data)
        if r['error_code'] == 429:
            await sendMessage(chat_id, f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after']+5} сек")
        elif r['error_code'] != 400:
            raise Exception(f"bad Keyboard: {r}\n")
        else: return
    return r['result']

async def editKeyboard(chat_id, message_id, keyboard):
    data = {
        'chat_id':chat_id,
        'message_id': message_id,
        'reply_markup': keyboard
    }

    response = await requests.post(TG_URL + 'editMessageReplyMarkup', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        if r['error_code'] == 429:
            await sendMessage(chat_id, f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after']+5} сек")
        elif r['error_code'] != 400:
            raise Exception(f"bad Keyboard edit: {r}")
        else: return
    return r['result']

async def sendAudio(chat_id, file = None, url = None, telegram_id = None, **kwargs):
    files = None
    if file:
        data = {
            'chat_id':chat_id
        }
        files = {'audio':file}
    elif url != None:
        data = {
            'chat_id':chat_id,
            'audio': url
        }
    elif telegram_id != None:
        data = {
            'chat_id':chat_id,
            'audio': telegram_id
        }
    else:
        raise Exception("Bad audio path!")

    data.update(kwargs)
    response = await requests.post(TG_URL + 'sendAudio', data = data, files = files, timeout=None)
    r = response.json()
    if not r['ok']:
        if r['error_code'] == 429:
            await sendMessage(chat_id, f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after']+5} сек")
        else:
            raise Exception(f"bad Audio: {r}")
    return r['result']

async def getChatMember(chat_id, user_id):
    data = {
        'chat_id': chat_id,
        'user_id': user_id
    }

    response = await requests.post(TG_URL + 'getChatMember', json = data, timeout=None)
    r = response.json()

    if not r['ok']:
        if false and r['error_code'] == 429:
            await sendMessage(chat_id, f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after']+5} сек")
        else:
            raise Exception(f"bad Message: {r}")
    return r['result']

#msg demon-worker functions
async def is_admin(msg):
    if msg['chat']['type'] == "private":
        return True
    if 'all_members_are_administrators' in msg['chat'] and msg['chat']['all_members_are_administrators']:
        return True
    chat_member = await getChatMember(msg['chat']['id'], msg['from']['id'])
    if chat_member['status'] == 'administrator' or chat_member['status'] == 'owner':
        return True
    return False

async def send_error( err):
    BOTLOG.info(ERROR_MSG)
    while True:
        try:
            await sendMessage(TG_SHELTER, ERROR_MSG+f"\nError: {repr(err)}")
        except Exception:
            await asyncio.sleep(60)
        else:
            break


#asynchronious workers
async def workerCommand(db, msg, command = None):
    if not command:
        command = msg['text'][1:]

    mail_id = command.find('@')
    if mail_id > -1:
        space_id = command.find(' ')
        if space_id > mail_id or space_id == -1:
            command = command[:mail_id+len(BOT_NAME)+1].lower().replace(f'@{BOT_NAME}','')+command[mail_id+len(BOT_NAME)+1:]

    if len(args := command.split())>1:
        command = args[0]
        args = args[1:]
    else:
        args = []

    BOTLOG.info(f"Command: /{command}")
    if command == "get_id":
        await sendMessage(
            msg['chat']['id'],
            f"This chat id: {msg['chat']['id']}\n"
        )
    if msg['chat']['id'] != TG_SHELTER and msg['chat']['id'] not in TG_CHANNELS:
        await sendMessage(
            msg['chat']['id'],
            NONPUBLIC_MSG
        )
        return

    if command == 'start':
        if 'username' in msg['from']:
            await sendKeyboard(msg['chat']['id'], \
                            f"Keyboard for @{msg['from'].get('username')}",
                            {'keyboard': MAIN_KEYBOARD,
                             'resize_keyboard': True,
                             'selective': True})
        else:
            await sendKeyboard(msg['chat']['id'], \
                            f"Keyboard for...",
                            {'keyboard': MAIN_KEYBOARD,
                             'resize_keyboard': True,
                             'selective': True},
                             reply_to_message_id = msg['message_id'])
    elif command == 'echo':
        await sendMessage(msg['chat']['id'], \
                            " ".join(args))
    elif command == 'help':
        await sendMessage(msg['chat']['id'], \
                            HELP_TEXT)
    elif command == 'about':
        await sendMessage(msg['chat']['id'], \
                            ABOUT_TEXT)
    elif command == 'settings':
        tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
        if 'username' in msg['from']:
            await sendKeyboard(msg['chat']['id'],
                                f"{msg['text']} for @{msg['from'].get('username')}",
                                {'keyboard': tmp_settings_keyboard,
                                 'resize_keyboard': True,
                                 'selective':True })
        else:
            await sendKeyboard(msg['chat']['id'],
                                f"{msg['text']} for...",
                                {'keyboard': tmp_settings_keyboard,
                                 'resize_keyboard': True,
                                 'selective':True },
                                 reply_to_message_id = msg['message_id'])

    elif command == 'get_stickers':
        await sendMessage(
            msg['chat']['id'],
            STIKERS_LINK,
            reply_to_message_id=msg['message_id']
        )
    elif command == "get_streams":
        table = ""
        for streamer in STREAMERS:
            table += f"Streamer {streamer['name']} is {'online' if streamer['online'] else 'offline'};\n"
        await sendMessage(
            msg['chat']['id'],
            table
        )
    #commands for admins
    elif msg['chat']['id'] == TG_SHELTER:
        if command == "sendecho":
            tmp_text = " ".join(args)
            await workerSender(db, tmp_text)
        elif command == "force_stream":
            for streamer in STREAMERS:
                if streamer["online"]:
                    await workerSender(db, build_stream_text(streamer))

async def workerMsg(db, msg):
    if 'text' in msg:
        if msg['text'][0] == '/':
            #if command
            await workerCommand(  db, msg)
        elif msg['text'] in KEYBOARD_COMMANDS:
            #if keyboard
            await workerCommand(  db, msg, KEYBOARD_COMMANDS[msg['text']])

async def workerCallback(db, callback):
    data = callback['data'].split('@')
    BOTLOG.info(f"Callback data: {data}")
    command, data = data[0], data[1:]

    if command == "pass":
        pass

async def workerSender(db, send_text):
    counter = 0
    async def sender(chat_id):
        nonlocal counter
        counter += 1
        await sendMessage(
            chat_id,
            send_text
        )
        counter -= 1

    for channel in TG_CHANNELS:
        asyncio.create_task(sender(channel))

    await sendMessage(
        TG_SHELTER,
        send_text
    )
    while counter>0:
        await asyncio.sleep(0)


async def mainWorker(db, result):
    try:
        if 'message' in result:
            if time.time() - result['message']['date'] > 5*60:
                BOTLOG.info("skip")
            else:
                await workerMsg(  db, result['message'])
        elif 'channel_post' in result:
            if time.time() - result['channel_post']['date'] > 5*60:
                BOTLOG.info("skip")
            else:
                await workerMsg(  db, result['channel_post'])
        #callback
        elif 'callback_query' in result:
            await workerCallback(  db, result['callback_query'])
        elif 'edited_message' in result:
            pass

    except Exception as err:
        asyncio.create_task(send_error(err))
        BOTLOG.exception(f"Error ocured {err}")
    return

#demons
async def streams_demon(db ):

    async def check_stream(streamer, trusted_deep=3):
        url = f"{streamer['platform']}/{streamer['id']}"
        #рекурсивная проверка
        #для удобства квостовая рекурсия переделана в цикл
        async def cicle_check():
            level = 1
            while(level <= trusted_deep):
                #если глубина проверки больше дозволеной то стрим оффлайн
                try:
                    #Воспользуемся API streamlink'а. Через сессию получаем инфу о стриме. Если инфы нет - то считаем за офлайн.
                    if SLS.streams(url):
                        return True #online
                except PluginError as err:
                    #если проблемы с интернетом
                    await asyncio.sleep(60)
                    continue
                level += 1
                #если говорит что стрим оффлайн проверим еще раз
            return False

        return await cicle_check()

    while ALIVE:
        try:
            for streamer in STREAMERS:
                online = await check_stream(streamer, 2)

                if online and not streamer["online"]:
                    await workerSender(db, build_stream_text(streamer))
                streamer["online"] = online
        except Exception as err:
            await send_error(err)
        await asyncio.sleep(30)


def pandora_box(db):
    asyncio.create_task(streams_demon(db))

#listeners
#~~flask~~ ~~vibora~~ sanic, requests
async def WHlistener(db):
    BOTLOG.info(f"Set Webhook...")
    #create ssl and webhook
    if SELF_SSL:
        #create ssl for webhook
        create_self_signed_cert(CERT_DIR)
        with open(os.path.join(CERT_DIR, CERT_FILE), "rb") as f:
            await setWebhook(WEBHOOK_URL, certificate = f)

        context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(
            os.path.join(CERT_DIR, CERT_FILE),
            keyfile=os.path.join(CERT_DIR, KEY_FILE)
        )
    else:
        await setWebhook(WEBHOOK_URL)

    response = (await getWebhookInfo()).json()
    if not response['ok']:
        BOTLOG.info("Webhook wasn't setted")
        BOTLOG.debug(pformat(response))
        BOTLOG.info(f"Shut down...")
        return

    BOTLOG.info("New webhook:")
    BOTLOG.info(f"\tUrl: {response['result']['url']}")
    BOTLOG.info(f"\tPending update: {response['result']['pending_update_count']}")
    BOTLOG.info(f"\tCustom certificate: {response['result']['has_custom_certificate']}")

    if response['result']['url'] != WEBHOOK_URL:
        BOTLOG.info(f"WebHook wasn't setted!")
        BOTLOG.info(f"Shut down...")
        return

    app_listener = Sanic(__name__)

    @app_listener.route(f'/{TG_TOKEN}/', methods = ['GET','POST'])
    async def receive_update(request):
        pprint(request.json)
        if request.method == "POST":
            await mainWorker(db, request.json)
        return sanic_json({"ok": True})

    BOTLOG.info(f"Listening...")
    server = app_listener.create_server(
        host = HOST_IP,
        port = PORT,
        return_asyncio_server=True,
        access_log = False,
        ssl = context if SELF_SSL else None
    )

    pandora_box(db)
    asyncio.create_task(server)
#requests only
async def LPlistener(db):
    LONGPOLING_OFFSET = 0
    LONGPOLING_DELAY = 3

    #offwebhook
    await setWebhook()

    pandora_box(db)
    #start listen
    BOTLOG.info(f"Listening...")
    while True:

        #get new messages
        success = False

        while not success:
            try:
                response = await requests.get(TG_URL + 'getUpdates',params =  {"offset":LONGPOLING_OFFSET}, timeout=None)
                r = response.json()
            except TimeoutError:
                pass
            else:
                success = r['ok']
            await asyncio.sleep(LONGPOLING_DELAY)

        #go to proceed all of them
        for result in r['result']:
            LONGPOLING_OFFSET = max(LONGPOLING_OFFSET,result['update_id'])+1
            asyncio.create_task(mainWorker(db, result))
#start func
def start_bot(WEB_HOOK_FLAG = True):

    BOTLOG.info(f"Start...")
    #print important constants
    BOTLOG.info(f"""
            {BOT_NAME=}
            {TG_TOKEN=}
            {TG_URL=}
            {TG_SHELTER=}
            {WEB_HOOK_FLAG=}
            {WEBHOOK_DOMEN=}
            {WEBHOOK_URL=}
            {SELF_SSL=}
            {HOST_IP=}
            {PORT=}""")

    try:
        #database loading
        BOTLOG.info(f"Database loading...")
        db_connect = sqlite3.connect("botbase.db")
        db_cursor = db_connect.cursor()

        db = namedtuple('Database', 'conn cursor')(conn = db_connect, cursor = db_cursor)

        #if new database
        #all_mode table
        db_cursor.execute(
            """CREATE TABLE IF NOT EXISTS chats
            (id TEXT PRIMARY KEY)""")


        db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        BOTLOG.info("TABLES:")
        for table in db_cursor.fetchall():
            BOTLOG.info(f"\t{table[0]}")

        loop = asyncio.get_event_loop()

        #pick type of listener and run
        asyncio.run(sendMessage(TG_SHELTER, START_MSG))
        loop.create_task((WHlistener if WEB_HOOK_FLAG else LPlistener)(db))
        loop.run_forever()

    except Exception as err:
        #Any error should send ping message to developer
        BOTLOG.info(FALL_MSG)
        while True:
            try:
                asyncio.run(sendMessage(TG_SHELTER, FALL_MSG))
            except Exception:
                time.sleep(60)
            else:
                break

        db_connect.close()
        loop.close()
        BOTLOG.exception(f"Error ocured {err}")
        raise(err)
    except BaseException as err:
        #Force exit with ctrl+C
        asyncio.run(sendMessage(TG_SHELTER, FINISH_MSG))
        db_connect.close()
        loop.close()
        BOTLOG.info(f"Force exit. {err}")
    finally:
        with open("botlogs.log", "r") as f:
            old_logs = f.read()
        with open("last_botlogs.log", "w") as f:
            f.write(old_logs)

if __name__ == "__main__":
    #parse args

    parser = argparse.ArgumentParser()
    parser.add_argument('-w', action="store", dest="webhook_on", default=1, type=int)
    parser.add_argument('-p', action="store", dest="port", default=None, type=int)
    parser.add_argument('-i', action="store", dest="ip", default=None)
    parser.add_argument('-d', action="store", dest="domen", default=None)
    parser.add_argument('-s', action="store", dest="ssl", default=None, type=int)
    args = parser.parse_args()

    if args.port: PORT = args.port
    if args.ip: HOST_IP = args.ip
    if args.domen:
        WEBHOOK_DOMEN = args.domen
        WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}:{PORT}/{TG_TOKEN}/"
    if args.ssl != None:
        SELF_SSL = bool(args.ssl)

    #if main then start bot
    start_bot(bool(args.webhook_on))
