from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import random, time, uuid, os
import logging
import time
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import threading
import logging
from zeroconf import ServiceInfo, Zeroconf
import http.client
import uuid
 
localHTTP = None
zeroconf = None
info = None
gwconnection = None

SNAP_COMMON = os.environ['SNAP_COMMON']
HOST = "a1x9b1ncwys18b-ats.iot.ap-southeast-1.amazonaws.com"
ROOT_CA = SNAP_COMMON + "/certs/root-CA.crt"
PRIVATE_KEY = SNAP_COMMON + "/certs/CLC_PRIVATE.pem.key"
CERT_FILE = SNAP_COMMON + "/certs/CLC_CERT.pem.crt"
PORT = 8883
CLIENT_ID = ""
TOPIC = ""
LOCAL_HOST = "smarthive-clc.local"
LOCAL_PORT = 4545



def mac_addr():
    return (':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
    for ele in range(0,8*6,8)][::-1]))  
    
# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)


# Custom MQTT message callback
def customCallback(client, userdata, message):
    logger.info("Received a new message: ")
    logger.info(message.payload)
    logger.info("from topic: ")
    logger.info(message.topic)
    payload = json.loads(message.payload)
    update_device_state(payload['hub_id'], payload['port'], payload['addr'], payload['state'])
    logger.info("--------------\n\n")

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
     # Create http connection to GW
     gwconnection = http.client.HTTPConnection("smarthive-gw.local", 80)
     #gwconnection = http.client.HTTPConnection("192.168.1.22", 80)
     gwconnection.set_debuglevel(10);
     gwconnection.request("POST", "/comm", json.dumps(payload), headers)
     response = gwconnection.getresponse()
     data = response.read()
     #logger.info(response.status, response.reason)
     logger.info(data)
     gwconnection.close()
    except Exception as e:
     logger.error("HTTP Error while update device")
     logger.error(e)

# Init AWSIoTMQTTClient
mqttClient = None
CLIENT_ID = mac_addr()
TOPIC = "smarthive/" + CLIENT_ID
logger.info("---------CLIENT_ID:" + CLIENT_ID)
logger.info("---------TOPIC:" + TOPIC)
mqttClient = AWSIoTMQTTClient(CLIENT_ID)
mqttClient.configureEndpoint(HOST, PORT)
mqttClient.configureCredentials(ROOT_CA, PRIVATE_KEY, CERT_FILE)

# AWSIoTMQTTClient connection configuration
mqttClient.configureAutoReconnectBackoffTime(1, 32, 20)
mqttClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
mqttClient.configureDrainingFrequency(2)  # Draining: 2 Hz
mqttClient.configureConnectDisconnectTimeout(10)  # 10 sec
mqttClient.configureMQTTOperationTimeout(5)  # 5 sec

# Connect and subscribe to AWS IoT
mqttClient.connect()
mqttClient.subscribe(TOPIC, 1, customCallback)
time.sleep(2)

def get_local_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("www.amazon.com", 80))
    res = s.getsockname()[0]
    s.close()
    return res


class CustomHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        # write the list of ip address as a response.
        logger.info("Received GET call ..........................")
        self.wfile.write("Hello World Smarthivedd~~")
        return

    def do_POST(self):
        logger.info("Received POST call ..........................")
        mqtt_publish("Hello World!!")
        self.send_response(200)
        return



def start():
    global localHTTP, zeroconf, info, httpthread
    ip = get_local_address()
    logging.info("Local IP is " + ip)
    desc = {"version": "0.1"}
    info = ServiceInfo(
        "_http._tcp.local.",
        "SmartHive._http._tcp.local.",
        socket.inet_aton(ip),
        LOCAL_PORT,
        0,
        0,
        desc,
        LOCAL_HOST + ".",
    )
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    logger.info("Local mDNS is started, domain is " + LOCAL_HOST)
    localHTTP = HTTPServer(("", LOCAL_PORT), CustomHandler)
    httpthread = threading.Thread(target=localHTTP.serve_forever)
    httpthread.start()

def mqtt_publish(message):
    messageJson = json.dumps(message)
    mqttClient.publish(TOPIC, messageJson, 1)
    logger.info("Published topic %s: %s\n" % (TOPIC, messageJson))


def main():
    start()

if __name__ == "__main__":
    main()
