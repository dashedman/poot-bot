import os
import json
# ssl generate lib
from OpenSSL import crypto

from config_structure import SSLConfig


def create_self_signed_cert(config: SSLConfig, domen):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)   # размер может быть 2048, 4196

    #  Создание сертификата
    cert = crypto.X509()
    cert.get_subject().C = "RU"   # указываем свои данные
    cert.get_subject().ST = "Saint-Petersburg"
    cert.get_subject().L = "Saint-Petersburg"   # указываем свои данные
    cert.get_subject().O = "musicforus"   # указываем свои данные
    cert.get_subject().CN = domen   # указываем свои данные
    cert.set_serial_number(1)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)   # срок "жизни" сертификата
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, b'SHA256')

    with open(os.path.join(config.cert_dir, config.cert_filename), "w") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii"))

    with open(os.path.join(config.cert_dir, config.key_filename), "w") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k).decode("ascii"))

    return crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("ascii")


def get_streamers():
    with open("streamers.json", "r", encoding='utf-8') as f:
        return json.load(f)


def set_streamers(streamers_update):
    with open("streamers.json", "w", encoding='utf-8') as f:
        json.dump(streamers_update, f, indent=4)
