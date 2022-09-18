import os
import argparse
import logging
from logging.handlers import TimedRotatingFileHandler

import main
from config_structure import MainConfig, TelegramConfig, DiscordConfig, SSLConfig, NetworkConfig


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

    file_log = TimedRotatingFileHandler(
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
    bot = main.PootBot(config)
    try:
        bot.start()
    except BaseException as err:
        out_logger = logging.getLogger('OUT LOGGER')
        out_logger.exception('Catch the BaseException', exc_info=err)
        raise err
