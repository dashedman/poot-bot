import json
from random import choice

MAIN_KEYBOARD = [[{'text':'🎭 Stickers'},{'text':'❓ Help'},{'text':'🔨 Settings'},{'text':'📔 About'}]]

SETTINGS_KEYBOARD = [[{'text':'↩️ Back'}]]

KEYBOARD_COMMANDS = { '❓ Help':'help',
                      '🔨 Settings':'settings',
                      '📔 About':'about',
                      '🎭 Stickers':'get_stickers',
                      '↩️ Back':'start'}

BAD_WORD = "*oh*"
START_MSG = "I'm on"
FINISH_MSG = "I'm off"
FALL_MSG = "I'm fall"
ERROR_MSG = "Catching the error :с\n"
NONPUBLIC_MSG = "Sorry.\nI don't work in other chats/groups/channels"
STIKERS_LINK = "t.me/addstickers/pootGard"
HELP_TEXT = """❓ Help

/start - to get Keyboard
/help - Help
/settings - Settings

/echo [text] - echo
/get_streams - to get stream status info
/get_stickers - to get pootGard stikers

/about - me c:
"""

ABOUT_TEXT = """📔 About!

📫 For any questions - telegram: @dashed_man

py3.8"""

def build_stream_text(streamer):
    with open("notificslist.json", "r", encoding='utf-8') as f:
        return [x.format(**streamer) for x in choice(json.load(f))]
