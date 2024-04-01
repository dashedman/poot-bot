import asyncio
import re
import logging
import time
from random import randint
from typing import List

import discord

import main
import ui_constants as uic
from config_structure import DiscordConfig


class DiscordSection:
    shelter: 'discord.TextChannel'
    channels: 'List[discord.TextChannel]'

    def __init__(self, main_bot: 'main.PootBot', config: 'DiscordConfig'):
        self.main_bot = main_bot
        self.config = config
        self.logger = logging.getLogger('dis_section')

        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)
        self.channels = []

        self.last_joke = 0
        self.joke_cooldown = 60 * 60

    async def load_channels(self):
        self.logger.info('Wait for client ready...')
        while not self.client.is_ready():
            await asyncio.sleep(0)

        self.logger.info('Channels prepearing!')
        self.shelter = self.client.get_channel(self.config.shelter)
        for it, channel_id in enumerate(self.config.channels):
            self.channels.append(self.client.get_channel(channel_id))

        t = f"DISCORD_SHELTER: {str(self.shelter)}\nDiscord channels:\n"
        for it, channel in enumerate(self.channels):
            t += f"\t{it+1}) {str(channel)}"
        self.logger.info(t, )

    async def demon(self):
        self.logger.info('Starting Discord Demon!')
        client = self.client

        @client.event
        async def on_message(message: discord.Message):
            self.logger.debug('@%s > "%s"', message.author, message.content)
            if message.author == self.client.user:
                return

            if len(message.content) < 1:
                return

            msg_parts = message.content.split(' ')
            command = args = None
            if msg_parts[0][0] == '!':
                command = msg_parts[0][1:]
                args = msg_parts[1:]

            if command is None and self.last_joke + self.joke_cooldown < time.time():
                self.last_joke = time.time()
                if msg_parts[0].lower() == "бля":
                    await message.channel.send("бля")
                elif message.content.lower() == "да":
                    await message.channel.send("пизда")

            elif command == 'echo':
                msg = re.sub(
                    r"<@.*?>", uic.BAD_WORD, ' '.join(args)
                ).replace(
                    "@here", uic.BAD_WORD
                ).replace("@everyone", uic.BAD_WORD)
                if msg:
                    await message.channel.send(msg)
            elif command == 'echot':
                msg = re.sub(
                    r"<@.*?>", uic.BAD_WORD, ' '.join(args)
                ).replace(
                    "@here", uic.BAD_WORD
                ).replace("@everyone", uic.BAD_WORD)
                if msg:
                    await message.delete()
                    await message.channel.send(msg)
            elif command == 'about':
                await message.channel.send(uic.ABOUT_TEXT)
            elif command == 'get_id':
                await message.channel.send(str(message.channel.id))
            elif command == '?':
                await message.channel.send("да" if randint(0, 1) else "нет")
            elif command == 'help':
                await message.channel.send("Не жди помощи. Этот мир прогнил...")

        await self.client.login(self.config.token)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.load_channels())
            try:
                await self.client.connect()
            except BaseException as err:
                self.logger.exception('ПИПАВСЬ!', exc_info=err)
                raise err
