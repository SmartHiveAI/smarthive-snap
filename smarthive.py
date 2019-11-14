from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import random, time, uuid, os, cgi, configparser
import logging, time, argparse, json
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket, threading, http.client, uuid
from zeroconf import ServiceInfo, ServiceBrowser, Zeroconf

SNAP_COMMON     = os.environ['SNAP_COMMON']
CONFIG_FOLDER   = SNAP_COMMON
LOCAL_HOST      = "smarthive-clc.local"
LOCAL_PORT      = 4545
CONFIG_FILE     = CONFIG_FOLDER + "/config.ini";
ROOT_CA         = CONFIG_FOLDER + "/certs/root-CA.crt"
PRIVATE_KEY     = CONFIG_FOLDER + "/certs/CLC_PRIVATE.pem.key"
CERT_FILE       = CONFIG_FOLDER + "/certs/CLC_CERT.pem.crt"
MQTT_HOST       = '' # "xxx.iot.zzz.amazonaws.com"
MQTT_PORT       = 0 # 8883
API_GATEWAY     = '' # "xxx.execute-api.zzz.amazonaws.com"
CLIENT_ID       = ''
TOPIC           = ''

gConfig = configparser.ConfigParser()
gSUList = None
gZeroconf = None
gMeshConnection = None
gApiGwConnection = None

def checkIsProvisioned():
    isProvisioned = False;
    certPath = CONFIG_FOLDER + "/certs";
    # check / create cert folder
    if not os.path.exists(certPath):
        try: os.mkdir(certPath)
        except OSError: logger.error("Creation directory failed: %s" % certPath)
        else: logger.info("Created directory: %s" % certPath)
    # check / create config file
    if (os.path.exists(CONFIG_FILE)):
        gConfig.read(CONFIG_FILE)
        try:
            global MQTT_HOST, MQTT_PORT, API_GATEWAY, gSUList
            MQTT_HOST = gConfig.get('default', 'MQTT_HOST').strip()
            MQTT_PORT = int(gConfig.get('default', 'MQTT_PORT'))
            API_GATEWAY = gConfig.get('default', 'API_GATEWAY')
            gSUList = gConfig.get('default', 'SU_LIST').split(",");
            isProvisioned = True;
        except Exception as e: logger.info('Configuration read Error: %s' % str(e))
    else:
        gConfig.add_section('default')
        gConfig.set('default', 'provisioned', 'no');
        with open(CONFIG_FILE, 'w') as configfile: gConfig.write(configfile)
    if isProvisioned == False:
        logger.info('Device not provisioned. Configuration pending.')
    return isProvisioned;

def startComms():
    psHelper = PubSubHelper();
    createGWConnection()
    createAPIConnection()

def mac_addr():
    return (':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
    for ele in range(0,8*6,8)][::-1]))

#Create gw connection
def createGWConnection():
    # Create http connection to GW
    global gMeshConnection
    entries = gZeroconf.cache.entries_with_name('SmartHive-GW.local.')
    if (len(entries) > 0):
        HOST_GW = str(entries[0])
        logger.info("Resolved SmartHive-GW IP: %s" % HOST_GW)
        gMeshConnection = http.client.HTTPConnection(HOST_GW, 80)
    else:
        logger.error('Could not resolve Gateway host')

def createAPIConnection():
    try:
        global gApiGwConnection
        gApiGwConnection = http.client.HTTPSConnection(API_GATEWAY)
        logger.info("Connecting to aws api gateway")
    except Exception as e:
        logger.error('Could not start API connection: %s' % str(e))

def get_mesh_config(payload):
    try:
        if gMeshConnection:
            gwHeaders = {'Content-type': 'application/json', 'X-Dest-Nodes': payload['hub_id'], 'X-Auth-Token': 'SmartHive00'}
            gMeshConnection.request("POST", "/comm", json.dumps(payload), gwHeaders)
            gwResponse = gMeshConnection.getresponse()
            gwResponseData = gwResponse.read()
            logger.info(gwResponseData)
            if gApiGwConnection:
                apiGWHeaders = {'Content-type': 'application/json'}
                apiResponsePayload = {}
                apiResponsePayload["status"] = "completed"
                apiResponsePayload["payload"] = gwResponseData
                gApiGwConnection.request("POST", "/prod/job/" + payload['requestId'], json.dumps(apiResponsePayload), apiGWHeaders)
                apiResponse = gApiGwConnection.getresponse()
                print(apiResponse)
                apiResponseData = apiResponse.read()
            else:
                logger.error("Could not send response to remote")
        else:
            logger.error('Could not resolve Gateway host')
    except Exception as e:
        logger.error("HTTP Error while update device")
        logger.error(e)

def update_device_state(hub_id, port, addr, state):
    try:
        headers = {'Content-type': 'application/json', 'X-Dest-Nodes': hub_id, 'X-Auth-Token': 'SmartHive00'}
        payload = {}
        payload['command'] = "set_thing"
        payload['port'] =  port
        payload['addr'] = int(addr)
        payload['state'] = int(state)
        # curl -XPOST https://xxx.co '{"op":"set", "clientId":"60:f8:1d:ce:86:84", "hub_id":"30aea4e7e41c", "port":"K", "addr":0, "state":1}'
        # curl -XPOST https://xxx.co '{"op":"set", "clientId":"60:f8:1d:ce:86:84", "hub_id":"30aea4e7e41c", "port":"K", "addr":0, "state":0}'
        if (gMeshConnection != None):
            gMeshConnection.request("POST", "/comm", json.dumps(payload), headers)
            response = gMeshConnection.getresponse()
            data = response.read()
            logger.info(data)
        else:
            logger.error('Could not resolve Gateway host')
    except Exception as e:
        logger.error("HTTP Error while update device")
        logger.error(e)

def get_local_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("www.amazon.com", 80))
    res = s.getsockname()[0]
    s.close()
    return res

class httpCallback(BaseHTTPRequestHandler):
    def do_GET(self):
        logger.info('Config data: %s' % json.dumps(dict(gConfig.items('default'))))
        self.send_response(200)
        self.wfile.write(json.dumps(dict(gConfig.items('default'))).encode())
        return

    def save_cert(self, fieldName, formData, dstFileName):
        filename = formData[fieldName].filename
        data = formData[fieldName].file.read()
        open(dstFileName, "wb").write(data)
        logger.info('Saved file: %s' % dstFileName)

    def do_POST(self):
        if checkIsProvisioned() == False:
            length = int(self.headers['content-length'])
            logger.info("Received POST: %s bytes" % length)
            if length > 10000000:
                logger.info("Uploaded file to big");
                read = 0
                while read < length: read += len(self.rfile.read(min(66556, length - read)))
                self.respond("Uploaded file to big")
                return
            else:
                formData = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE':self.headers['Content-Type']})
                logger.debug(formData)
                try:
                    self.save_cert('rootCert', formData, ROOT_CA)
                    self.save_cert('deviceCert', formData, CERT_FILE)
                    self.save_cert('privateKey', formData, PRIVATE_KEY)
                except:
                    logger.error('Parameter error. Required parameter missing.');
                    self.send_response(400, 'Bad request')

                try:
                    #gConfig.add_section('default')
                    gConfig.set('default', 'provisioned', 'yes');
                    gConfig.set('default', 'SU_LIST', formData.getvalue('suList'));
                    gConfig.set('default', 'MQTT_HOST', formData.getvalue('mqttHost'));
                    gConfig.set('default', 'MQTT_PORT', formData.getvalue('mqttPort'));
                    gConfig.set('default', 'API_GATEWAY', formData.getvalue('apiGateway'));
                    gConfig.set('default', 'TOPIC', TOPIC)
                    gConfig.set('default', 'CLIENT_ID', CLIENT_ID)
                    gConfig.set('default', 'ROOT_CA', ROOT_CA)
                    gConfig.set('default', 'CERT_FILE', CERT_FILE)
                    gConfig.set('default', 'PRIVATE_KEY', PRIVATE_KEY)

                    with open(CONFIG_FILE, 'w') as configfile: gConfig.write(configfile)
                    if checkIsProvisioned() == True: startComms()
                    self.send_response(200)
                    self.wfile.write("Device provisioning successsful".encode())
                    return
                except Exception as e:
                    logger.error('Could not save config: %s' % str(e));
                    self.send_response(500, 'Internal server error')
                    return
        else:
            self.send_response(400, 'Bad request')
            self.wfile.write("Device already provisioned".encode())
        return

class mdnsListener:
    def remove_service(self, zeroconf, type, name):
        logger.info("Service removed: %s" % (name,))
    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        logger.info("Service added: %s, ip: %s" % (name, zeroconf.cache.entries_with_name('SmartHive-GW.local.')))

class PubSubHelper:
    def __init__(self):
        global CLIENT_ID, TOPIC
        # Init AWSIoTMQTTClient
        self.mqttClient = None
        logger.info("MQTT config - ClientId: %s, Topic: %s" % (CLIENT_ID, TOPIC))
        self.mqttClient = AWSIoTMQTTClient(CLIENT_ID)
        self.mqttClient.configureEndpoint(MQTT_HOST, MQTT_PORT)
        self.mqttClient.configureCredentials(ROOT_CA, PRIVATE_KEY, CERT_FILE)
        # AWSIoTMQTTClient connection configuration
        self.mqttClient.configureAutoReconnectBackoffTime(1, 32, 20)
        self.mqttClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
        self.mqttClient.configureDrainingFrequency(2)  # Draining: 2 Hz
        self.mqttClient.configureConnectDisconnectTimeout(10)  # 10 sec
        self.mqttClient.configureMQTTOperationTimeout(5)  # 5 sec
        # Connect and subscribe to AWS IoT
        self.mqttClient.connect()
        self.mqttClient.subscribe(TOPIC, 1, self.mqttCallback)
        time.sleep(2)

    def mqtt_publish(self, message):
        messageJson = json.dumps(message)
        this.mqttClient.publish(TOPIC, messageJson, 1)
        logger.info("Published topic %s: %s\n" % (TOPIC, messageJson))

    def mqttCallback(client, userdata, message):
        logger.info("Received message [%s]: %s" % (message.topic, message.payload))
        payload = json.loads(message.payload)
        if(payload['command']) == 'set_thing':
            update_device_state(payload['hub_id'], payload['port'], payload['addr'], payload['state'])
        if(payload['command']) == 'get_mesh_config':
            get_mesh_config(payload)

def main():
    global gZeroconf, CLIENT_ID, TOPIC
    CLIENT_ID = mac_addr()
    TOPIC = "smarthive/" + CLIENT_ID
    # MDNS
    gZeroconf = Zeroconf()
    info = ServiceInfo("_http._tcp.local.", "SmartHive-CLC._http._tcp.local.", socket.inet_aton(get_local_address()), LOCAL_PORT, 0, 0, {"version": "0.1"}, LOCAL_HOST + ".")
    gZeroconf.register_service(info)
    listener = mdnsListener()
    browser = ServiceBrowser(gZeroconf, "_http._tcp.local.", listener)
    logger.info("Local mDNS on domain: " + LOCAL_HOST)
    # Check for provisioning and config
    isProvisioned = checkIsProvisioned();
    if isProvisioned == True: startComms()
    # local http server
    localHTTP = HTTPServer(("", LOCAL_PORT), httpCallback)
    httpthread = threading.Thread(target=localHTTP.serve_forever)
    httpthread.start()

if __name__ == "__main__":
    # Configure logging
    logger = logging.getLogger("AWSIoTPythonSDK.core")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    streamHandler = logging.StreamHandler()
    streamHandler.setFormatter(formatter)
    logger.addHandler(streamHandler)
    main()
