"""
SmartHive Snap
"""
import os
import cgi
import sys
import json
import uuid
import logging
import configparser
import http.client
import socket
import threading
import AWSIoTPythonSDK
from zeroconf import ServiceInfo, Zeroconf, DNSAddress
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from http.server import BaseHTTPRequestHandler
from urllib3 import HTTPSConnectionPool
from http.server import HTTPServer

SH_CONFIG = configparser.ConfigParser()

LOGGER = logging.getLogger("SmartHive")
LOGGER.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
LOGGER.addHandler(stream_handler)

MQTT_HOST = ''  # "xxx.iot.zzz.amazonaws.com"
MQTT_PORT = 0  # 8883
API_GATEWAY = ''  # "xxx.execute-api.zzz.amazonaws.com"
SU_LIST = None
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

class MQTTHelper:
    '''Helper class to receive commands over MQTT, pass through to Mesh and respond back to the cloud gateway'''

    def __init__(self):
        self.conn_mgr = HTTPConnPoolMgr()
        LOGGER.info("MQTT config - ClientId: %s, Topic: %s", CLIENT_ID, TOPIC)
        self.mqtt_client = None
        self.mqtt_client = AWSIoTMQTTClient(CLIENT_ID)
        self.mqtt_client.configureEndpoint(MQTT_HOST, MQTT_PORT)
        self.mqtt_client.configureCredentials(ROOT_CA, PRIVATE_KEY, CERT_FILE)
        self.mqtt_client.configureAutoReconnectBackoffTime(1, 60, 10)  # 1 - 60 seconds backoff, 10 sec stable reset
        self.mqtt_client.configureOfflinePublishQueueing(100, AWSIoTPythonSDK.MQTTLib.DROP_OLDEST)  # queue 100 requests
        self.mqtt_client.configureDrainingFrequency(2)  # Draining: 2 Hz
        self.mqtt_client.configureConnectDisconnectTimeout(10)  # 10 sec
        self.mqtt_client.configureMQTTOperationTimeout(5)  # 5 sec
        self.mqtt_client.enableMetricsCollection()
        self.mqtt_client.onOffline = self.onOffline_callback
        self.mqtt_client.onOnline = self.onOnline_callback
        self.mqtt_client.connect(60)
        self.mqtt_client.subscribe(TOPIC, 1, self.mqtt_callback)
        # self.heartbeat()
        # time.sleep(2)

    def onOffline_callback(self):
        LOGGER.info("<------MQTT OFFLINE------>")

    def onOnline_callback(self):
        LOGGER.info("<------MQTT ONLINE------>")

    def mqtt_publish(self, topic, message):
        '''Send data over MQTT'''
        message_str = json.dumps(message)
        self.mqtt_client.publish(TOPIC, message_str, 1)
        LOGGER.info("Published topic %s: %s", TOPIC, message_str)

    def mqtt_callback(self, client, userdata, message):
        '''Received data over MQTT'''
        LOGGER.info("Received message [%s]: %s", message.topic, message.payload.decode("utf-8"))
        self.pass_thru_command(message.payload)

    def send_one_command(self, headers, command):
        '''Send on command to the mesh gateway over HTTP'''
        LOGGER.info('Command for Mesh Root: %s', command)
        mesh_response = self.conn_mgr.sendMeshCommand(headers, json.dumps(command))
        LOGGER.info('Response from Mesh Root: %s', mesh_response)
        return mesh_response

    def pass_thru_command(self, content):
        '''Pass through command(s) received via MQTT to the Mesh'''
        payload = json.loads(content.decode("utf-8"))
        try:
            mesh_response = None
            if 'command' in payload['content']:
                mesh_headers = {'Content-type': 'application/json', 'X-Dest-Nodes': payload['headers']['X-Dest-Nodes'], 'X-Auth-Token': payload['headers']['X-Auth-Token']}
                mesh_response = self.send_one_command(mesh_headers, payload['content'])
            else:
                # Hetero hub commands
                for command_id in payload['content']:
                    if mesh_response is None:
                        mesh_response = {}
                    mesh_headers = {'Content-type': 'application/json', 'X-Dest-Nodes': payload['content'][command_id]['hub'].replace(":", ""), 'X-Auth-Token': payload['headers']['X-Auth-Token']}
                    mesh_response[command_id] = self.send_one_command(mesh_headers, payload['content'][command_id])
            if 'requestId' in payload:
                api_status_payload = {}
                api_headers = {'Content-type': 'application/json'}
                api_status_payload["status"] = "completed"
                api_status_payload["payload"] = json.dumps(mesh_response)
                api_response = self.conn_mgr.sendJobStatusRequest(payload['requestId'], api_headers, json.dumps(api_status_payload))
                LOGGER.info('Response from API GW: %s', api_response)
            else:
                LOGGER.info('Heartbeat command')
        except Exception as e:
            LOGGER.error("pass_thru_command Error: %s", str(e))

    def heartbeat(self):
        try:
            payload = {'headers': {'X-Dest-Nodes': 'ffffffffffff', 'X-Auth-Token': 'SmartHive00'}, 'content': {'command': 'get_mesh_config'}}
            LOGGER.info('Sending HEARTBEAT: %s', payload)
            self.mqtt_publish(TOPIC, payload)
            threading.Timer(900, self.heartbeat).start()
        except Exception as e:
            LOGGER.info('Failed to send heartbeat: %s', str(e))


class MDNSHelper:
    '''MDNS management ... mainly looking for mesh gateway node'''
    ip_addr = ""
    zeroconf = Zeroconf()
    info = None

    def __init__(self):
        self.get_local_address()
        self.info = ServiceInfo("_http._tcp.local.", SVC_NAME + "._http._tcp.local.", socket.inet_aton(self.ip_addr), SVC_PORT, 0, 0, {"version": "0.1"}, SVC_NAME + ".local.")
        self.zeroconf.register_service(self.info)
        LOGGER.info("Local mDNS on domain: %s", SVC_NAME)

    # def __del__(self):
    #    LOGGER.info("Unregistering ...")
    #    self.zeroconf.unregister_service(self.info)
    #    self.zeroconf.close()

    def get_local_address(self):
        '''Try to get local address'''
        try:
            self.ip_addr = socket.gethostbyname_ex(socket.gethostname())[-1][1]
        except IndexError:
            if len(self.ip_addr) == 0:
                sock_fd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock_fd.connect(("www.google.com", 80))
                self.ip_addr = sock_fd.getsockname()[0]
                sock_fd.close()
        except socket.error as e_sock:
            LOGGER.error("No Ip from gethostbyname_ex: %s", str(e_sock))
        finally:
            LOGGER.info("Local IP address: %s", self.ip_addr)

    @staticmethod
    def resolve_mdns(name):
        '''Get address from cache or perform an mDNS query'''
        ip_addr = None
        try:
            cache = MDNSHelper.zeroconf.cache.cache
            value = cache.get(name.lower() + ".local.")
            if value is not None and len(value) > 0 and isinstance(value[0], DNSAddress):
                ip_addr = socket.inet_ntoa(value[0].address)
                LOGGER.info("Cache - %s", ip_addr)
            if ip_addr is None:
                info = MDNSHelper.zeroconf.get_service_info("_http._tcp.local.", name + "._http._tcp.local.")
                if info is not None:
                    ip_addr = socket.inet_ntoa(info.address)
                    LOGGER.info("Active resolution - %s", ip_addr)
        except Exception as e_fail:
            LOGGER.error("Could not resolve service: %s - %s", name, str(e_fail))
        return ip_addr


def check_provisioned():
    '''Check if Hub has been factory provisioned with the right certs'''
    is_provisioned = False
    cert_path = CONFIG_FOLDER + "/certs"
    if not os.path.exists(cert_path):
        try:
            os.mkdir(cert_path)
        except OSError:
            LOGGER.error("Creation directory failed: %s", cert_path)
        else:
            LOGGER.info("Created directory: %s", cert_path)
    if os.path.exists(CONFIG_FILE):
        SH_CONFIG.read(CONFIG_FILE)
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
        with open(CONFIG_FILE, 'w') as configfile:
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
                    self.save_cert('rootCert', form_data, ROOT_CA)
                    self.save_cert('deviceCert', form_data, CERT_FILE)
                    self.save_cert('privateKey', form_data, PRIVATE_KEY)
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
                SH_CONFIG.set('default', 'TOPIC', TOPIC)
                SH_CONFIG.set('default', 'CLIENT_ID', CLIENT_ID)
                SH_CONFIG.set('default', 'ROOT_CA', ROOT_CA)
                SH_CONFIG.set('default', 'CERT_FILE', CERT_FILE)
                SH_CONFIG.set('default', 'PRIVATE_KEY', PRIVATE_KEY)
                with open(CONFIG_FILE, 'w') as configfile:
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


def main():
    '''Main entry point - configures and starts - logger, mdns, provisioning check and http'''
    LOGGER.info('Starting SmartHive Cloud Controller ...')
    # MDNS
    MDNSHelper()
    MDNSHelper.resolve_mdns("SmartHive-GW")
    # while True:
    #    mdns_helper.resolve_mdns("SmartHive-GW")
    #    time.sleep(10)
    # Check for provisioning status and config
    is_provisioned = check_provisioned()
    LOGGER.info("Provisioned status: %s", is_provisioned)
    if is_provisioned is True:
        MQTTHelper()
    # Local http server
    local_svr = HTTPServer(("", SVC_PORT), HTTPHelper)
    httpthread = threading.Thread(target=local_svr.serve_forever)
    httpthread.start()


if __name__ == "__main__":
    main()
