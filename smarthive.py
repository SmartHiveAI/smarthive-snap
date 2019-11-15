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
# Configure logging
gLogger = logging.getLogger("AWSIoTPythonSDK.core")
gLogger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
gLogger.addHandler(streamHandler)
gLogger.info('Starting SmartHive Cloud Controller ...');

def checkIsProvisioned():
    isProvisioned = False;
    certPath = CONFIG_FOLDER + "/certs";
    # check / create cert folder
    if not os.path.exists(certPath):
        try: os.mkdir(certPath)
        except OSError: gLogger.error("Creation directory failed: %s" % certPath)
        else: gLogger.info("Created directory: %s" % certPath)
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
        except Exception as e: gLogger.info('Configuration read Error: %s' % str(e))
    else:
        gConfig.add_section('default')
        gConfig.set('default', 'provisioned', 'no');
        with open(CONFIG_FILE, 'w') as configfile: gConfig.write(configfile)
    gLogger.debug(json.dumps(dict(gConfig.items('default'))))
    if isProvisioned == False:
        gLogger.info('Device not provisioned. Configuration pending.')
    return isProvisioned;

def startComms():
    psHelper = PubSubHelper();
    createGWConnection()
    createAPIConnection()

def mac_addr():
    return (':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
    for ele in range(0,8*6,8)][::-1]))

# Create gw connection
# TODO: check connection for disconnects and reconnect
def createGWConnection():
    # Create http connection to GW
    global gZeroconf, gMeshConnection
    entries = gZeroconf.cache.entries_with_name('SmartHive-GW.local.')
    if (len(entries) > 0):
        HOST_GW = str(entries[0])
        gLogger.info("Resolved SmartHive-GW IP: %s" % HOST_GW)
        if gMeshConnection: gMeshConnection.close()
        gMeshConnection = http.client.HTTPConnection(HOST_GW, 80)
    else:
        gLogger.error('Could not resolve Gateway host')

def createAPIConnection():
    try:
        global gApiGwConnection
        if gApiGwConnection: gApiGwConnection.close()
        gApiGwConnection = http.client.HTTPSConnection(API_GATEWAY)
        gLogger.info("Connecting to aws api gateway")
    except Exception as e:
        gLogger.error('Could not start API connection: %s' % str(e))

def get_local_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("www.amazon.com", 80))
    res = s.getsockname()[0]
    s.close()
    return res

class httpCallback(BaseHTTPRequestHandler):
    def sendResponse(self, code, message, body):
        self.send_response(code, message)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body.encode())

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "content-type,x-auth-token")
        self.end_headers()
        return

    def do_GET(self):
        authToken = self.headers['X-Auth-Token']
        if gSUList != None and authToken not in gSUList:
            self.sendResponse(400, 'Bad request', "Invalid credentials. Contact device owner.");
            return
        configJson = json.dumps(dict(gConfig.items('default')))
        gLogger.info('Config data: %s' % configJson)
        self.sendResponse(200, 'ok', configJson);
        return

    def save_cert(self, fieldName, formData, dstFileName):
        filename = formData[fieldName].filename
        data = formData[fieldName].file.read()
        open(dstFileName, "wb").write(data)
        gLogger.info('Saved file: %s' % dstFileName)

    def do_POST(self):
        length = int(self.headers['content-length'])
        gLogger.info("Received POST: %s bytes" % length)
        if length > 10000000:
            gLogger.info("Uploaded file to big");
            read = 0
            while read < length: read += len(self.rfile.read(min(66556, length - read)))
            self.respond("Uploaded file to big")
            return
        else:
            formData = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST', 'CONTENT_TYPE':self.headers['Content-Type']})
            authToken = self.headers['X-Auth-Token']
            gLogger.debug(formData)
            isProvisioned = checkIsProvisioned();
            if isProvisioned == True and authToken == None:
                self.sendResponse(400, 'Bad request', "Device already provisioned");
                return
            elif isProvisioned == True and authToken != None and authToken not in gSUList:
                self.sendResponse(400, 'Bad request', "Invalid credentials. Contact device owner.");
                return

            if isProvisioned == False:
                try:
                    self.save_cert('rootCert', formData, ROOT_CA)
                    self.save_cert('deviceCert', formData, CERT_FILE)
                    self.save_cert('privateKey', formData, PRIVATE_KEY)
                except:
                    gLogger.error('Parameter error. Required parameter missing.');
                    self.sendResponse(400, 'Bad request', "Parameter error. Required parameter missing.");
                    return;
            try:
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
                self.sendResponse(200, 'ok', "Device provisioning successsful");
                return
            except Exception as e:
                gLogger.error('Could not save config: %s' % str(e));
                self.sendResponse(500, 'Internal server error', 'Internal Server Error');
                return
        return

class mdnsListener:
    def remove_service(self, zeroconf, type, name):
        gLogger.info("Service removed: %s" % (name,))
    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        gLogger.info("Service added: %s, ip: %s" % (name, zeroconf.cache.entries_with_name('SmartHive-GW.local.')))

class PubSubHelper:
    def pass_thru_command(self, content):
        payload = json.loads(content.decode("utf-8"))
        try:
            if gMeshConnection:
                gwHeaders = {'Content-type': 'application/json', 'X-Dest-Nodes': payload['headers']['X-Dest-Nodes'], 'X-Auth-Token': payload['headers']['X-Auth-Token']}
                gMeshConnection.request("POST", "/comm", json.dumps(payload['content']), gwHeaders)
                gwResponse = gMeshConnection.getresponse()
                gwResponseData = gwResponse.read().decode("utf-8")
                gLogger.info('Response from Mesh Root: %s' % gwResponseData)
                if gApiGwConnection:
                    apiGWHeaders = {'Content-type': 'application/json'}
                    apiResponsePayload = {}
                    apiResponsePayload["status"] = "completed"
                    apiResponsePayload["payload"] = gwResponseData
                    gApiGwConnection.request("POST", "/prod/job/" + payload['requestId'], json.dumps(apiResponsePayload), apiGWHeaders)
                    apiResponse = gApiGwConnection.getresponse()
                    gLogger.info('Response from API GW' % apiResponse.read().decode("utf-8"))
                    apiResponseData = apiResponse.read()
                else: gLogger.error("Could not send response to remote")
            else: gLogger.error('Could not resolve Gateway host')
        except Exception as e:
            gLogger.error("pass_thru_command Error: %s" % str(e))

    def __init__(self):
        global CLIENT_ID, TOPIC
        # Init AWSIoTMQTTClient
        self.mqttClient = None
        gLogger.info("MQTT config - ClientId: %s, Topic: %s" % (CLIENT_ID, TOPIC))
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
        gLogger.info("Published topic %s: %s\n" % (TOPIC, messageJson))

    def mqttCallback(self, client, userdata, message):
        gLogger.info("Received message [%s]: %s" % (message.topic, message.payload.decode("utf-8")))
        self.pass_thru_command(message.payload)

def main():
    global gZeroconf, CLIENT_ID, TOPIC
    CLIENT_ID = mac_addr()
    TOPIC = "smarthive/" + CLIENT_ID.replace(":", "")
    # MDNS
    gZeroconf = Zeroconf()
    info = ServiceInfo("_http._tcp.local.", "SmartHive-CLC._http._tcp.local.", socket.inet_aton(get_local_address()), LOCAL_PORT, 0, 0, {"version": "0.1"}, LOCAL_HOST + ".")
    gZeroconf.register_service(info)
    listener = mdnsListener()
    browser = ServiceBrowser(gZeroconf, "_http._tcp.local.", listener)
    gLogger.info("Local mDNS on domain: " + LOCAL_HOST)
    # Check for provisioning and config
    isProvisioned = checkIsProvisioned();
    if isProvisioned == True: startComms()
    # local http server
    localHTTP = HTTPServer(("", LOCAL_PORT), httpCallback)
    httpthread = threading.Thread(target=localHTTP.serve_forever)
    httpthread.start()

if __name__ == "__main__":
    main()
