from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import random, time, uuid, os

SNAP_COMMON = os.environ['SNAP_DATA'] + '/../common/';
SHADOW_CLIENT = "SmartHiveCLC"
HOST_NAME = "a1x9b1ncwys18b-ats.iot.ap-southeast-1.amazonaws.com"
ROOT_CA = SNAP_COMMON + "/certs/AmazonRootCA1.pem"
PRIVATE_KEY = SNAP_COMMON + "/certs/private.pem.key"
CERT_FILE = SNAP_COMMON + "/certs/certificate.pem.crt"
SHADOW_HANDLER = "clc-dev-002"

uuid = hex(uuid.getnode());

def myShadowUpdateCallback(payload, responseStatus, token):
  print()
  print('UPDATE: $aws/things/' + SHADOW_HANDLER + '/shadow/update/#')
  print("payload = " + payload)
  print("responseStatus = " + responseStatus)
  print("token = " + token)

# Create, configure, and connect a shadow client.
myShadowClient = AWSIoTMQTTShadowClient(SHADOW_CLIENT)
myShadowClient.configureEndpoint(HOST_NAME, 8883)
myShadowClient.configureCredentials(ROOT_CA, PRIVATE_KEY, CERT_FILE)
myShadowClient.configureConnectDisconnectTimeout(10)
myShadowClient.configureMQTTOperationTimeout(5)
myShadowClient.connect()

myDeviceShadow = myShadowClient.createShadowHandlerWithName(SHADOW_HANDLER, True)

def main():
    print(os.environ['SNAP']);
    print(os.environ['SNAP_DATA']);
    print(os.environ['SNAP_USER_DATA']);
    print(SNAP_COMMON);

    while True:
      moisture = random.choice([True, False])
      if moisture:
        myDeviceShadow.shadowUpdate('{"state":{"reported":{"moisture":"okay"}}}', myShadowUpdateCallback, 5)
      else:
        myDeviceShadow.shadowUpdate('{"state":{"reported":{"moisture":"low"}}}', myShadowUpdateCallback, 5)
      time.sleep(60)

#if __name__== "__main__":
#    main()
