'''HTTP server functions'''
import os
import cgi
import sys
import json
import logging
import configparser
import http.client
from http.server import BaseHTTPRequestHandler
from urllib3 import HTTPSConnectionPool

import defines
from mdns_helper import MDNSHelper

SH_CONFIG = configparser.ConfigParser()

MQTT_HOST = ''  # "xxx.iot.zzz.amazonaws.com"
MQTT_PORT = 0  # 8883
API_GATEWAY = ''  # "xxx.execute-api.zzz.amazonaws.com"
SU_LIST = None

LOGGER = logging.getLogger("SmartHive.HTTP")


def check_provisioned():
    '''Check if Hub has been factory provisioned with the right certs'''
    is_provisioned = False
    cert_path = defines.CONFIG_FOLDER + "/certs"
    if not os.path.exists(cert_path):
        try:
            os.mkdir(cert_path)
        except OSError:
            LOGGER.error("Creation directory failed: %s", cert_path)
        else:
            LOGGER.info("Created directory: %s", cert_path)
    if os.path.exists(defines.CONFIG_FILE):
        SH_CONFIG.read(defines.CONFIG_FILE)
        try:
            global MQTT_HOST, MQTT_PORT, API_GATEWAY, SU_LIST
            MQTT_HOST = SH_CONFIG.get('default', 'MQTT_HOST').strip()
            MQTT_PORT = int(SH_CONFIG.get('default', 'MQTT_PORT'))
            API_GATEWAY = SH_CONFIG.get('default', 'API_GATEWAY')
            SU_LIST = list(json.loads(SH_CONFIG.get('default', 'SU_LIST')).values())
            is_provisioned = True
        except Exception as e:
            LOGGER.info('Configuration read Error: %s', str(e))
    else:
        SH_CONFIG.add_section('default')
        SH_CONFIG.set('default', 'provisioned', 'no')
        with open(defines.CONFIG_FILE, 'w') as configfile:
            SH_CONFIG.write(configfile)
    LOGGER.debug(json.dumps(dict(SH_CONFIG.items('default'))))
    if is_provisioned is False:
        LOGGER.info('Device not provisioned. Configuration pending.')
    return is_provisioned


class HTTPConnPoolMgr:
    '''Manage Connection pools for the cloud gateway and the local mesh'''
    def __init__(self):
        self.api_pool = HTTPSConnectionPool(API_GATEWAY, port=443, maxsize=10, block=True, headers=None)

    def sendJobStatusRequest(self, requestId, headers, payload):
        '''Send back job status to the Cloud gateway'''
        response = self.api_pool.request("POST", "/prod/job/" + requestId, body=payload, headers=headers)
        LOGGER.info('API Pool Status: %d conn, %d requests', self.api_pool.num_connections, self.api_pool.num_requests)
        return response.data.decode("utf-8")

    def sendMeshCommand(self, headers, payload):
        '''Send one command to the mesh over HTTP'''
        gateway_host = MDNSHelper.resolve_mdns("SmartHive-GW")
        mesh_conn = http.client.HTTPConnection(gateway_host, 80)
        #response = self.mesh_pool.request("POST", "/comm", body=payload, headers=headers)
        mesh_conn.request("POST", "/comm", json.dumps(payload), headers)
        gw_response = mesh_conn.getresponse()
        return gw_response.read().decode("utf-8")


class HTTPHelper(BaseHTTPRequestHandler):
    '''HTTP handler functions for the local HTTP server'''

    def __init__(self):
        super(HTTPHelper, self).__init__()
        LOGGER.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        LOGGER.addHandler(stream_handler)

    def send_cors_response(self, code, message, body):
        self.send_response(code, message)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body.encode())

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'content-type,x-auth-token')
        self.end_headers()

    def do_GET(self):
        auth_token = self.headers['X-Auth-Token']
        if SU_LIST != None and (auth_token not in SU_LIST and 'SmartHive00' not in SU_LIST):
            self.send_cors_response(400, 'Bad request', 'Invalid credentials. Contact device owner.')
            return
        configJson = json.dumps(dict(SH_CONFIG.items('default')))
        LOGGER.info('Config data: %s', configJson)
        self.send_cors_response(200, 'ok', configJson)

    def save_cert(self, fieldName, form_data, dstFileName):
        data = form_data[fieldName].file.read()
        open(dstFileName, "wb").write(data)
        LOGGER.info('Saved file: %s', dstFileName)

    def do_POST(self):
        length = int(self.headers['content-length'])
        LOGGER.info("Received POST: %s bytes", length)
        if length > 10000000:
            LOGGER.info('Uploaded file to big')
            read = 0
            while read < length:
                read += len(self.rfile.read(min(66556, length - read)))
            self.send_cors_response(400, 'Bad Request', 'Uploaded file to big')
            return
        else:
            form_data = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']})
            auth_token = self.headers['X-Auth-Token']
            LOGGER.debug(form_data)
            is_provisioned = check_provisioned()
            if is_provisioned is True and auth_token is None:
                self.send_cors_response(400, 'Bad request', 'Device already provisioned')
                return
            elif is_provisioned is True and auth_token is not None and 'SmartHive00' in SU_LIST:
                # 'SmartHive00' - default factory provisioned, not claimed yet, will be removed once claimed
                pass
            elif is_provisioned is True and auth_token is not None and auth_token not in SU_LIST:
                self.send_cors_response(400, 'Bad request', 'Invalid credentials. Contact device owner.')
                return

            '''
            Provisioning request:
            curl                                                                                                    \
                -F 'rootCert=@root.crt' -F 'deviceCert=@device.crt' -F 'privateKey=@private.key'                    \
                -F 'mqttHost=xxxx' -F 'mqttPort=yyyy' -F 'apiGateway=zzzz' -F 'suList=aaaa,bbbb'                    \
                http://smarthive-clc.local:4545/
            '''
            if is_provisioned is False:
                try:
                    self.save_cert('rootCert', form_data, defines.ROOT_CA)
                    self.save_cert('deviceCert', form_data, defines.CERT_FILE)
                    self.save_cert('privateKey', form_data, defines.PRIVATE_KEY)
                except Exception as e:
                    LOGGER.error('Parameter error. Required parameter missing. %s', e)
                    self.send_cors_response(400, 'Bad request', "Parameter error. Required parameter missing.")
                    return
            try:
                SH_CONFIG.set('default', 'provisioned', 'yes')
                SH_CONFIG.set('default', 'SU_LIST', form_data.getvalue('suList'))
                SH_CONFIG.set('default', 'MQTT_HOST', form_data.getvalue('mqttHost'))
                SH_CONFIG.set('default', 'MQTT_PORT', form_data.getvalue('mqttPort'))
                SH_CONFIG.set('default', 'API_GATEWAY', form_data.getvalue('apiGateway'))
                SH_CONFIG.set('default', 'TOPIC', defines.TOPIC)
                SH_CONFIG.set('default', 'CLIENT_ID', defines.CLIENT_ID)
                SH_CONFIG.set('default', 'ROOT_CA', defines.ROOT_CA)
                SH_CONFIG.set('default', 'CERT_FILE', defines.CERT_FILE)
                SH_CONFIG.set('default', 'PRIVATE_KEY', defines.PRIVATE_KEY)
                with open(defines.CONFIG_FILE, 'w') as configfile:
                    SH_CONFIG.write(configfile)
                if check_provisioned():
                    sys.exit()
                self.send_cors_response(200, 'ok', '{ "message": "Device provisioning successsful" }')
                return
            except Exception as e:
                LOGGER.error('Could not save config: %s', str(e))
                self.send_cors_response(500, 'Internal server error', 'Internal Server Error')
                return
        return
