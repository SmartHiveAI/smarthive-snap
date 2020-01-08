'''Global defines'''
import os
import uuid

SNAP_COMMON = os.environ['SNAP_COMMON']
CONFIG_FOLDER = SNAP_COMMON
CONFIG_FILE = CONFIG_FOLDER + "/config.ini"
ROOT_CA = CONFIG_FOLDER + "/certs/root-CA.crt"
PRIVATE_KEY = CONFIG_FOLDER + "/certs/CLC_PRIVATE.pem.key"
CERT_FILE = CONFIG_FOLDER + "/certs/CLC_CERT.pem.crt"
CLIENT_ID = (':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0, 8*6, 8)][::-1]))
TOPIC = "smarthive/" + CLIENT_ID.replace(":", "")

SVC_NAME = "SmartHive-CLC"
SVC_PORT = 4545
