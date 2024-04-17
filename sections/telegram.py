import json
import os
import asyncio
import logging
import ssl
import time
from pprint import pformat

import aiohttp.web
import aiohttp.client_exceptions

import main
import utils
import ui_constants as uic
from config_structure import TelegramConfig


class TelegramSection:

    def __init__(self, main_bot, config):
        self.main_bot: 'main.PootBot' = main_bot
        self.config: 'TelegramConfig' = config
        self.logger = logging.getLogger('tg_section')

    def listener(self):
        if self.config.is_webhook:
            return self.wh_listener()
        else:
            return self.lp_listener()

    async def lp_listener(self):
        longpoling_offset = 0
        longpoling_delay = 3

        # offwebhook
        await self.set_webhook()

        # start listen
        self.logger.info(f"Listening...")

        async with asyncio.TaskGroup() as tg:
            while True:

                # get new messages
                success = False
                r = None

                while not success:
                    request_url = self.config.url + 'getUpdates'
                    request_params = {"offset": longpoling_offset}
                    try:
                        async with aiohttp.ClientSession(timeout=None) as session:
                            async with session.get(request_url, params=request_params) as response:
                                r = await response.json()
                    except (TimeoutError, aiohttp.client_exceptions.ClientConnectionError):
                        pass
                    except json.JSONDecodeError as exc:
                        self.logger.warning(
                            'Catch JSON decode error!\nRequest:\n%s\n.\n',
                            f'Url: {request_url}\nParams: {request_params}',
                            exc_info=exc
                        )
                    else:
                        success = r['ok']
                    await asyncio.sleep(longpoling_delay)

                # go to proceed all of them
                for result in r['result']:
                    longpoling_offset = max(longpoling_offset, result['update_id']) + 1
                    tg.create_task(self.main_worker(result))

    async def wh_listener(self):
        self.logger.info(f"Set Webhook...")
        # create ssl and webhook
        ssl_conf = self.main_bot.config.ssl
        network = self.main_bot.config.network
        webhook_url = network.webhook_url + self.config.token + '/'

        if ssl_conf.self_ssl:
            # create ssl for webhook
            utils.create_self_signed_cert(
                ssl_conf,
                network.webhook_domen,
            )
            with open(os.path.join(ssl_conf.cert_dir, ssl_conf.cert_filename), "rb") as f:
                await self.set_webhook(webhook_url, certificate=f)

            context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(
                os.path.join(ssl_conf.cert_dir, ssl_conf.cert_filename),
                keyfile=os.path.join(ssl_conf.cert_dir, ssl_conf.key_filename)
            )
        else:
            context = None
            await self.set_webhook(webhook_url)

        response = await self.get_webhook_info()
        if not response['ok']:
            self.logger.info("Webhook wasn't setted")
            self.logger.debug(pformat(response))
            self.logger.info(f"Shut down...")
            return

        self.logger.info("New webhook:")
        self.logger.info(f"\tUrl: {response['result']['url']}")
        self.logger.info(f"\tPending update: {response['result']['pending_update_count']}")
        self.logger.info(f"\tCustom certificate: {response['result']['has_custom_certificate']}")

        if response['result']['url'] != webhook_url:
            self.logger.info(f"WebHook wasn't setted!")
            self.logger.info(f"Shut down...")
            return

        app_listener = aiohttp.web.Application()

        async def receive_update(request):
            if request.method == "POST":
                await self.main_worker(request.json)
            return aiohttp.web.json_response({"ok": True})

        app_listener.add_routes([
            aiohttp.web.get(f'/{self.config.token}/', receive_update),
            aiohttp.web.post(f'/{self.config.token}/', receive_update),
        ])

        self.logger.info(f"Listening...")
        runner = aiohttp.web.AppRunner(app_listener)
        await runner.setup()
        site = aiohttp.web.TCPSite(
            runner,
            host=network.host_ip,
            port=network.port,
            ssl_context=context if ssl_conf.self_ssl else None)
        await site.start()
        return asyncio.Future()     # forever future

    # tg send functions
    async def main_worker(self, result):
        try:
            if 'message' in result:
                if time.time() - result['message']['date'] > 5 * 60:
                    self.logger.info("skip")
                else:
                    await self.worker_msg(result['message'])
            elif 'channel_post' in result:
                if time.time() - result['channel_post']['date'] > 5 * 60:
                    self.logger.info("skip")
                else:
                    await self.worker_msg(result['channel_post'])
            # callback
            elif 'callback_query' in result:
                await self.worker_callback(result['callback_query'])
            elif 'edited_message' in result:
                pass

        except Exception as err:
            self.logger.exception(f"Error occured!", exc_info=err)
        return

    async def worker_msg(self, msg):
        if 'text' in msg:
            if msg['text'][0] == '/':
                # if command
                await self.main_bot.worker_command(msg)
            elif msg['text'] in uic.KEYBOARD_COMMANDS:
                # if keyboard
                await self.main_bot.worker_command(msg, uic.KEYBOARD_COMMANDS[msg['text']])

    async def worker_callback(self, callback):
        data = callback['data'].split('@')
        self.logger.info(f"Callback data: {data}")
        command, data = data[0], data[1:]

        if command == "pass":
            pass

    async def send_message(self, chat_id, text, **kwargs):
        data = {
            'chat_id': chat_id,
            'text': text
        }
        data.update(kwargs)

        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(self.config.url + 'sendMessage', json=data) as response:
                r = await response.json()

        if not r['ok']:
            if r['error_code'] == 429:
                await self.send_message(
                    chat_id,
                    f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after'] + 5} сек")
            else:
                raise Exception(f"bad Message: {r}")
        return r['result']

    async def send_keyboard(self, chat_id, text, keyboard, **kwargs):
        data = {
            'chat_id': chat_id,
            'text': text,
            'reply_markup': keyboard
        }
        data.update(kwargs)

        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(self.config.url + 'sendMessage', json=data) as response:
                r = await response.json()

        if not r['ok']:
            self.logger.info(pformat(r))
            if r['error_code'] == 429:
                await self.send_message(
                    chat_id,
                    f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after'] + 5} сек")
            elif r['error_code'] != 400:
                raise Exception(f"bad Keyboard: {r}\n")
            else:
                return
        return r['result']

    async def edit_keyboard(self, chat_id, message_id, keyboard):
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'reply_markup': keyboard
        }

        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(self.config.url + 'editMessageReplyMarkup', json=data) as response:
                r = await response.json()

        if not r['ok']:
            if r['error_code'] == 429:
                await self.send_message(
                    chat_id,
                    f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after'] + 5} сек")
            elif r['error_code'] != 400:
                raise Exception(f"bad Keyboard edit: {r}")
            else:
                return
        return r['result']

    async def get_chat_member(self, chat_id, user_id):
        data = {
            'chat_id': chat_id,
            'user_id': user_id
        }

        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(self.config.url + 'getChatMember', json=data) as response:
                r = await response.json()

        if not r['ok']:
            if r['error_code'] == 429:
                await self.send_message(
                    chat_id,
                    f"Слишком много запросов! Пожалуйста повторите через {r['parameters']['retry_after'] + 5} сек")
            else:
                raise Exception(f"bad Message: {r}")
        return r['result']

    # msg demon-worker functions
    async def is_admin(self, msg):
        if msg['chat']['type'] == "private":
            return True
        if 'all_members_are_administrators' in msg['chat'] and msg['chat']['all_members_are_administrators']:
            return True
        chat_member = await self.get_chat_member(msg['chat']['id'], msg['from']['id'])
        if chat_member['status'] == 'administrator' or chat_member['status'] == 'owner':
            return True
        return False

    async def set_webhook(self, url='', certificate=None):
        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(
                self.config.url + 'setWebhook',
                json={'url': url},
                data={'certificate': certificate} if certificate else None
            ) as response:
                r = await response.json()

    async def get_webhook_info(self):
        async with aiohttp.ClientSession(timeout=None) as session:
            async with session.post(self.config.url + 'getWebhookInfo') as response:
                r = await response.json()
                return r
