import asyncio
import argparse
import os
import logging
import logging.handlers
import signal

from collections import namedtuple
from copy import deepcopy


# streamlink lib
from streamlink import Streamlink, PluginError

import utils
import sections
# my local lib
from ui_constants import *
from config_structure import MainConfig, TelegramConfig, DiscordConfig, SSLConfig, NetworkConfig


# StreamLink Session
SLS = Streamlink()
# SLS.load_plugins("streamlink_plugins/")
SLS.set_plugin_option("twitch", "disable_hosting", True)
SLS.set_plugin_option("twitch", "disable_reruns", True)
SLS.set_plugin_option("twitch", "disable-ads", True)


class PootBot:
    loop: 'asyncio.AbstractEventLoop'
    discord: 'sections.DiscordSection'
    telegram: 'sections.TelegramSection'
    db: 'namedtuple'

    def __init__(self, mconfig: 'MainConfig'):
        self.logger = logging.getLogger("bot")
        self.config = mconfig

        self.alive = True

    # start func
    def start(self):

        self.logger.info(f"Start...")
        # print important constants
        self.logger.info(self.config.pretty_str())

        self.loop = asyncio.get_event_loop()
        try:
            self.loop.add_signal_handler(signal.SIGINT, lambda: self.loop.stop())
            self.loop.add_signal_handler(signal.SIGTERM, lambda: self.loop.stop())
        except NotImplementedError:
            pass

        self.discord = sections.DiscordSection(self, self.config.discord, self.loop)
        self.telegram = sections.TelegramSection(self, self.config.telegram, self.loop)

        self.loop.run_until_complete(self.run())

    async def run(self):
        try:
            await asyncio.gather(
                self.telegram.listener(),
                self.discord.demon(),
                self.streams_demon(),
            )
        except Exception as err:
            # Any error should send ping message to developer
            self.logger.info(FALL_MSG)
            self.logger.exception(f"Error ocured {err}")
            raise err
        except BaseException as err:
            # Force exit with ctrl+C
            await self.discord.client.close()
            self.logger.info(f"Force exit. {err}")
            raise

    async def worker_command(self, msg, command=None):
        if not command:
            command = msg['text'][1:]

        mail_id = command.find('@')
        if mail_id > -1:
            space_id = command.find(' ')
            if space_id > mail_id or space_id == -1:
                # restructured `command@bot some` to `command some`
                command = command[:mail_id + len(self.config.bot_name) + 1]\
                              .lower()\
                              .replace(f'@{self.config.bot_name}', '') \
                          + command[mail_id + len(self.config.bot_name) + 1:]

        if len(command_args := command.split()) > 1:
            command = command_args[0]
            command_args = command_args[1:]
        else:
            command_args = []

        self.logger.info(f"Command: /{command}")
        if command == "get_id":
            await self.telegram.send_message(
                msg['chat']['id'],
                f"This chat id: {msg['chat']['id']}\n"
            )

        if command == 'start':
            if 'username' in msg['from']:
                await self.telegram.send_keyboard(
                    msg['chat']['id'],
                    f"Keyboard for @{msg['from'].get('username')}",
                    {
                        'keyboard': MAIN_KEYBOARD,
                        'resize_keyboard': True,
                        'selective': True
                    })
            else:
                await self.telegram.send_keyboard(
                    msg['chat']['id'],
                    f"Keyboard for...",
                    {
                        'keyboard': MAIN_KEYBOARD,
                        'resize_keyboard': True,
                        'selective': True
                    },
                    reply_to_message_id=msg['message_id'])
        elif command == 'echo':
            await self.telegram.send_message(msg['chat']['id'],
                                             " ".join(command_args))
        elif command == 'help':
            await self.telegram.send_message(msg['chat']['id'],
                                             HELP_TEXT)
        elif command == 'about':
            await self.telegram.send_message(msg['chat']['id'],
                                             ABOUT_TEXT)
        elif command == 'settings':
            tmp_settings_keyboard = deepcopy(SETTINGS_KEYBOARD)
            if 'username' in msg['from']:
                await self.telegram.send_keyboard(
                    msg['chat']['id'],
                    f"{msg['text']} for @{msg['from'].get('username')}",
                    {
                        'keyboard': tmp_settings_keyboard,
                        'resize_keyboard': True,
                        'selective': True
                    })
            else:
                await self.telegram.send_keyboard(
                    msg['chat']['id'],
                    f"{msg['text']} for...",
                    {
                        'keyboard': tmp_settings_keyboard,
                        'resize_keyboard': True,
                        'selective': True
                    },
                    reply_to_message_id=msg['message_id'])

        elif command == 'get_stickers':
            await self.telegram.send_message(
                msg['chat']['id'],
                STIKERS_LINK,
                reply_to_message_id=msg['message_id']
            )
        elif command == "get_streams":
            table = ""
            for streamer in utils.get_streamers():
                table += f"Streamer {streamer['name']} is {'online' if streamer['online'] else 'offline'};\n"
            await self.telegram.send_message(
                msg['chat']['id'],
                table
            )
        # commands for admins
        elif msg['chat']['id'] == self.config.telegram.shelter:
            if command == "sendecho":
                tmp_text = " ".join(command_args)
                await self.worker_sender([tmp_text] * 2)
            if command == "testecho":
                tmp_text = " ".join(command_args)
                await self.telegram.send_message(self.config.telegram.shelter, tmp_text)
                await self.discord.shelter.send(tmp_text)
            elif command == "force_stream":
                for streamer in utils.get_streamers():
                    if streamer["online"]:
                        await self.worker_sender(build_stream_text(streamer))
            elif command == "test_stream":
                tmp_text = build_stream_text({
                    "platform": "test.tv",
                    "name": "Test Streamer (test)",
                    "id": "teststreamer",
                    "online": True
                })
                await self.telegram.send_message(self.config.telegram.shelter, tmp_text[0])
                await self.discord.shelter.send(tmp_text[1])

    async def worker_sender(self, send_text):
        counter = 0

        async def sender(send_func):
            nonlocal counter
            counter += 1
            await send_func
            counter -= 1

        # asyncio.create_task(sender(self.telegram.send_message(
        #     TG_SHELTER,
        #     send_text[0]
        # )))
        for channel in self.config.telegram.channels:
            asyncio.create_task(sender(self.telegram.send_message(
                channel,
                send_text[0]
            )))

        for channel in self.discord.channels:
            asyncio.create_task(sender(channel.send(send_text[1])))

        while counter > 0:
            await asyncio.sleep(0)

    # demons
    async def streams_demon(self):

        async def check_stream(streamer_, trusted_deep=3):
            url = f"{streamer_['platform']}/{streamer_['id']}"

            # рекурсивная проверка
            # для удобства хвостовая рекурсия переделана в цикл
            async def cicle_check():
                level = 1
                while level <= trusted_deep:
                    # если глубина проверки больше дозволеной то стрим оффлайн
                    try:
                        # Воспользуемся API streamlink'а. Через сессию получаем инфу о стриме. Если инфы нет - то считаем за офлайн.
                        res = await self.loop.run_in_executor(
                            None,
                            SLS.streams, url
                        )
                        if res:
                            return True  # online
                    except PluginError:
                        # если проблемы с интернетом
                        await asyncio.sleep(60)
                    level += 1
                    # если говорит что стрим оффлайн проверим еще раз
                return False

            return await cicle_check()

        # online profilactic
        streamers = utils.get_streamers()
        for streamer in streamers:
            streamer['online'] = True
        utils.set_streamers(streamers)

        while self.alive:
            try:
                for streamer in (streamers := utils.get_streamers()):
                    online = await check_stream(streamer, 2)
                    self.logger.info(f"{streamer['name']} [{streamer['online']} -> {online}]")

                    if online and not streamer["online"]:
                        await self.worker_sender(build_stream_text(streamer))
                    streamer["online"] = online
                utils.set_streamers(streamers)

            except Exception as err:
                self.logger.exception('Catch error in streams demon!', exc_info=err)
            await asyncio.sleep(30)


if __name__ == "__main__":

    with open("config.ini", "r") as f:
        bot_name = f.readline()[:-1]
        wb_domen = f.readline()[:-1]
        host_ip = f.readline()[:-1]
        tg_token = f.readline()[:-1]
        dis_token = f.readline()[:-1]

    port = os.environ.get('PORT') or 443
    is_self_ssl = True

    # parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('-w', action="store", dest="webhook_on", default=0, type=int)
    parser.add_argument('-p', action="store", dest="port", default=None, type=int)
    parser.add_argument('-i', action="store", dest="ip", default=None)
    parser.add_argument('-d', action="store", dest="domen", default=None)
    parser.add_argument('-s', action="store", dest="ssl", default=None, type=int)
    parser.add_argument('-b', action="store", dest="bugs", default=None, type=int)
    args = parser.parse_args()

    logs_path = 'logs'
    if not os.path.isdir(logs_path):
        os.mkdir(logs_path)

    file_log = logging.handlers.TimedRotatingFileHandler(
        f'{logs_path}/logs.txt',
        when='D',
        backupCount=14,
        encoding='utf-8',
    )
    console_out = logging.StreamHandler()
    logging.basicConfig(
        handlers=(file_log, console_out),
        format='[%(asctime)s | %(levelname)s] %(name)s: %(message)s',
        datefmt='%a %b %d %H:%M:%S %Y',
        level=logging.DEBUG if args.bugs else logging.INFO
    )

    if args.port:
        port = args.port
    if args.ip:
        host_ip = args.ip
    if args.domen:
        wb_domen = args.domen
    if args.ssl is not None:
        is_self_ssl = bool(args.ssl)

    network_config = NetworkConfig(
        webhook_domen=wb_domen,
        host_ip=host_ip,
        port=port,
    )

    ssl_config = SSLConfig(
        pkey_filename="bot.pem",
        key_filename="bot.key",
        cert_filename="bot.crt",
        cert_dir="",
        self_ssl=is_self_ssl,
    )

    telegram_config = TelegramConfig(
        token=tg_token,
        is_webhook=bool(args.webhook_on),
        shelter=-1001483908315,
        channels=[
            -1001461862272,  # chanel
            -1001450762287  # group
        ]
    )

    discord_config = DiscordConfig(
        token=dis_token,
        shelter=758297066635132959,
        channels=[
            600446916286742538,
        ]
    )

    config = MainConfig(
        bot_name=bot_name,
        network=network_config,
        ssl=ssl_config,
        telegram=telegram_config,
        discord=discord_config,
    )

    # if main then start bot
    bot = PootBot(config)
    bot.start()
