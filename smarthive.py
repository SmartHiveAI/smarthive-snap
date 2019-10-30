from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import random, time, uuid, os
import logging
import time
import argparse
import json
from  http.server import BaseHTTPRequestHandler,HTTPServer
import socket
import threading
import logging
from zeroconf import ServiceInfo, Zeroconf

localHTTP = None
zeroconf = None
info = None

SNAP_COMMON = "/home/pi/"
HOST = "a1x9b1ncwys18b-ats.iot.ap-southeast-1.amazonaws.com"
ROOT_CA = SNAP_COMMON + "certs/root-CA.crt"
PRIVATE_KEY = SNAP_COMMON + "certs/clc-us-001.private.key"
CERT_FILE = SNAP_COMMON + "certs/clc-us-001.cert.pem"
PORT = 8883
CLIENT_ID = "basicPubSub"
TOPIC = "sdk/test/Python"
LOCAL_HOST = "smarthive-clc.local"
LOCAL_PORT = 4545

#uuid = hex(uuid.getnode());

# Custom MQTT message callback
def customCallback(client, userdata, message):
    print("Received a new message: ")
    print(message.payload)
    print("from topic: ")
    print(message.topic)
    print("--------------\n\n")


# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

# Init AWSIoTMQTTClient
myAWSIoTMQTTClient = None
myAWSIoTMQTTClient = AWSIoTMQTTClient(CLIENT_ID)
myAWSIoTMQTTClient.configureEndpoint(HOST, PORT)
myAWSIoTMQTTClient.configureCredentials(ROOT_CA, PRIVATE_KEY, CERT_FILE)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

# Connect and subscribe to AWS IoT
myAWSIoTMQTTClient.connect()
myAWSIoTMQTTClient.subscribe(TOPIC, 1, customCallback)
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
      self.send_header('Content-type','text/html')
      self.end_headers()
      # write the list of ip address as a response. 
      self.wfile.write("Hello World Smarthivedd~~")
      return
    def do_POST(self):
	    mqtt_publish("Hello World!!")
      self.send_response(200)
      return


def start():
	global localHTTP, zeroconf, info, httpthread
	ip = get_local_address()
	logging.info("Local IP is " + ip)
	print("Starting ..........." + ip)
	desc = {'version': '0.1'}

  	info = ServiceInfo("_http._tcp.local.",
			"SmartHive._http._tcp.local.",
			socket.inet_aton(ip), LOCAL_PORT, 0, 0,
			desc, LOCAL_HOST + ".")

	zeroconf = Zeroconf()
	zeroconf.register_service(info)
	print("Local mDNS is started, domain is " + LOCAL_HOST)
	localHTTP = HTTPServer(("", LOCAL_PORT), CustomHandler)
	httpthread = threading.Thread(target=localHTTP.serve_forever)
	httpthread.start()
	print("Local HTTP is " + ip)  


def mqtt_publish(message):
     messageJson = json.dumps(message)   
     myAWSIoTMQTTClient.publish(TOPIC, messageJson, 1)
     print('Published topic %s: %s\n' % (TOPIC, messageJson))


def main():
    start()

if __name__== "__main__":
    main()
