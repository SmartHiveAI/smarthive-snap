from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import random, time, uuid, os

SNAP_COMMON = os.environ['SNAP_DATA'];
HOST = "a1x9b1ncwys18b-ats.iot.ap-southeast-1.amazonaws.com"
ROOT_CA = SNAP_COMMON + "/certs/AmazonRootCA1.pem"
PRIVATE_KEY = SNAP_COMMON + "/certs/private.pem.key"
CERT_FILE = SNAP_COMMON + "/certs/certificate.pem.crt"
PORT = 8883
CLIENT_ID = "SMARTHIVE-001"

uuid = hex(uuid.getnode());

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
myAWSIoTMQTTClient.subscribe(topic, 1, customCallback)
time.sleep(2)

def main():
    print(os.environ['SNAP']);
    print(os.environ['SNAP_DATA']);
    print(os.environ['SNAP_USER_DATA']);
    print(SNAP_COMMON);

    loopCount = 0
    while True:
        message = {}
        message['message'] = args.message
        message['sequence'] = loopCount
        messageJson = json.dumps(message)
        myAWSIoTMQTTClient.publish(topic, messageJson, 1)
        if args.mode == 'publish':
            print('Published topic %s: %s\n' % (topic, messageJson))
        loopCount += 1
      time.sleep(1)
#if __name__== "__main__":
#    main()
