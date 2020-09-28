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
import signal

from pprint import pprint, pformat
from collections import namedtuple, deque
from copy import deepcopy
from functools import partial
from random import randint

#discord api
import discord

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


with open("config.ini","r") as f:
    BOT_NAME = f.readline()[:-1]
    WEBHOOK_DOMEN = f.readline()[:-1]
    HOST_IP = f.readline()[:-1]
    TG_TOKEN = f.readline()[:-1]
    DIS_TOKEN = f.readline()[:-1]



PORT = os.environ.get('PORT') or 443

TG_URL = "https://api.telegram.org/bot"+ TG_TOKEN +"/"
TG_SHELTER = -1001483908315
DIS_CLIENT = None
DIS_SHELTER = 758297066635132959
WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}:{PORT}/{TG_TOKEN}/"

PKEY_FILE = "bot.pem"
KEY_FILE = "bot.key"
CERT_FILE = "bot.crt"
CERT_DIR = ""
SELF_SSL = True
ALIVE = True


TG_CHANNELS = [
    -1001461862272
]
DIS_CHANNELS = [
    600446916286742538,
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

def get_streamers():
    with open("streamers.json","r",encoding='utf-8') as f:
        return json.load(f)

def set_streamers(streamers_update):
    with open("streamers.json","w",encoding='utf-8') as f:
        json.dump(streamers_update, f, indent = 4)

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
        for streamer in get_streamers():
            table += f"Streamer {streamer['name']} is {'online' if streamer['online'] else 'offline'};\n"
        await sendMessage(
            msg['chat']['id'],
            table
        )
    #commands for admins
    elif msg['chat']['id'] == TG_SHELTER:
        if command == "sendecho":
            tmp_text = " ".join(args)
            await workerSender(db, [tmp_text]*2)
        if command == "testecho":
            tmp_text = " ".join(args)
            await sendMessage(TG_SHELTER, tmp_text)
            await DIS_SHELTER.send(tmp_text)
        elif command == "force_stream":
            for streamer in get_streamers():
                if streamer["online"]:
                    await workerSender(db, build_stream_text(streamer))
        elif command == "test_stream":
            tmp_text = build_stream_text({
                "platform": "test.tv",
                "name": "Test Streamer (test)",
                "id": "teststreamer",
                "online": True
            })
            await sendMessage(TG_SHELTER, tmp_text[0])
            await DIS_SHELTER.send(tmp_text[1])

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
    async def sender(send_func):
        nonlocal counter
        counter += 1
        await send_func
        counter -= 1

    for channel in TG_CHANNELS:
        asyncio.create_task(sender(sendMessage(
            channel,
            send_text[0]
        )))

    for channel in DIS_CHANNELS:
        asyncio.create_task(sender(channel.send(send_text[1])))

    await sendMessage(
        TG_SHELTER,
        send_text[0]
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

    #online profilactic
    streamers = get_streamers()
    for streamer in streamers:
        streamer['online'] = True
    set_streamers(streamers)

    while ALIVE:
        try:
            for streamer in (streamers := get_streamers()):
                online = await check_stream(streamer, 2)

                if online and not streamer["online"]:
                    await workerSender(db, build_stream_text(streamer))
                streamer["online"] = online
            set_streamers(streamers)

        except Exception as err:
            await send_error(err)
        await asyncio.sleep(30)

async def discord_demon(db ):
    global DIS_SHELTER

    async def load_channels():
        global DIS_SHELTER
        while not DIS_CLIENT.is_ready():
            await asyncio.sleep(0)

        DIS_SHELTER = DIS_CLIENT.get_channel(DIS_SHELTER)
        for it, channel in enumerate(DIS_CHANNELS):
            DIS_CHANNELS[it] = DIS_CLIENT.get_channel(channel)

        t = f"DISCORD_SHELTER: {str(DIS_SHELTER)}\nDiscord channels:\n"
        for it, channel in enumerate(DIS_CHANNELS):
            t += f"\t{it+1}) {str(channel)}"
        await DIS_SHELTER.send(t)

    @DIS_CLIENT.event
    async def on_message(message):
        if message.author == DIS_CLIENT.user:
            return

        if len(message.content) < 1:
            return
        msg_parts = message.content.split(' ')
        command = None
        if msg_parts[0][0] == '!':
            command = msg_parts[0][1:]
            args = msg_parts[1:]

        if command is None:
            if msg_parts[0].lower() == "бля":
                await message.channel.send("бля")
            if message.content.lower() == "да":
                await message.channel.send("пизда")

        elif command == 'echo':
            msg = re.sub(r"<@.*?>", BAD_WORD, ' '.join(args)).replace("@here", BAD_WORD).replace("@everyone", BAD_WORD)
            if msg:
                await message.channel.send(msg)
        elif command == 'echot':
            msg = re.sub(r"<@.*?>", BAD_WORD, ' '.join(args)).replace("@here", BAD_WORD).replace("@everyone", BAD_WORD)
            if msg:
                await message.delete()
                await message.channel.send(msg)
        elif command == 'about':
            await message.channel.send(ABOUT_TEXT)
        elif command == 'get_id':
            await message.channel.send(message.channel.id)
        elif command == '?':
            await message.channel.send("да" if randint(0,1) else "нет")

    await DIS_CLIENT.login(DIS_TOKEN)
    asyncio.create_task(load_channels())
    try:
        await DIS_CLIENT.connect()
    except BaseException:
        print("ПИПАВСЬ")
        raise

def pandora_box(db):
    asyncio.create_task(discord_demon(db))
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
            {DIS_TOKEN=}
            {DIS_SHELTER=}
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

        db = namedtuple('Database', 'connect cursor')(connect = db_connect, cursor = db_cursor)

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
        try:
            loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
            loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
        except NotImplementedError:
            pass

        global DIS_CLIENT
        DIS_CLIENT = discord.Client(loop = loop)
        #pick type of listener and run
        loop.create_task((WHlistener if WEB_HOOK_FLAG else LPlistener)(db))
        loop.run_forever()

    except Exception as err:
        #Any error should send ping message to developer
        BOTLOG.info(FALL_MSG)
        BOTLOG.exception(f"Error ocured {err}")
        while True:
            try:
                asyncio.run(sendMessage(TG_SHELTER, FALL_MSG))
            except Exception:
                time.sleep(60)
            else:
                break
        raise(err)
    except BaseException as err:
        #Force exit with ctrl+C
        asyncio.run(DIS_CLIENT.logout())
        BOTLOG.info(f"Force exit. {err}")
    finally:
        db.connect.close()
        loop.close()
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
    parser.add_argument('-b', action="store", dest="bugs", default=None, type=int)
    args = parser.parse_args()

    file_log = logging.FileHandler("botlogs.log", mode = "w")
    console_out = logging.StreamHandler()
    logging.basicConfig(
        handlers=(file_log, console_out),
        format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
        datefmt='%a %b %d %H:%M:%S %Y',
        level=logging.DEBUG if args.bugs else logging.INFO)
    BOTLOG = logging.getLogger("bot")

    if args.port: PORT = args.port
    if args.ip: HOST_IP = args.ip
    if args.domen: WEBHOOK_DOMEN = args.domen
    WEBHOOK_URL = f"https://{WEBHOOK_DOMEN}:{PORT}/{TG_TOKEN}/"
    if args.ssl != None:
        SELF_SSL = bool(args.ssl)

    #if main then start bot
    start_bot(bool(args.webhook_on))
