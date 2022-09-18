from functools import cached_property
from dataclasses import dataclass, fields


@dataclass
class PrettyString:

    def pfields(self):
        for field in fields(self):
            yield field.name, getattr(self, field.name)

    def fields_str(self) -> list[str]:
        lines = []

        for field_name, field in self.pfields():
            if isinstance(field, PrettyString):
                lines.append(str(field_name) + ':')
                sub_lines = field.fields_str()
                lines.extend(
                    '  ' + line for line in sub_lines
                )
            else:
                lines.append(str(field_name) + ': ' + str(field))

        return lines

    def pretty_str(self):
        main_str = ''.join(
            line + '\n' for line in self.fields_str()
        )
        return main_str


@dataclass
class TelegramConfig(PrettyString):
    token: str
    is_webhook: bool
    shelter: int
    channels: list[int]

    @cached_property
    def url(self):
        return "https://api.telegram.org/bot" + self.token + "/"


@dataclass
class DiscordConfig(PrettyString):
    token: str
    shelter: int
    channels: list[int]


@dataclass
class NetworkConfig(PrettyString):
    webhook_domen: str
    host_ip: str
    port: int

    @cached_property
    def webhook_url(self):
        return f"https://{self.webhook_domen}:{self.port}/"


@dataclass
class SSLConfig(PrettyString):
    pkey_filename: str
    key_filename: str
    cert_filename: str
    cert_dir: str
    self_ssl: bool


@dataclass
class MainConfig(PrettyString):
    bot_name: str

    network: NetworkConfig
    ssl: SSLConfig

    telegram: TelegramConfig
    discord: DiscordConfig
