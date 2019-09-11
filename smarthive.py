from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import random, time, uuid

SHADOW_CLIENT = "SmartHiveCLC"
HOST_NAME = "a1x9b1ncwys18b-ats.iot.ap-southeast-1.amazonaws.com"
ROOT_CA = "/certs/AmazonRootCA1.pem"
PRIVATE_KEY = "/certs/4ad641e2bc-private.pem.key"
CERT_FILE = "/certs/4ad641e2bc-certificate.pem.crt"
SHADOW_HANDLER = "clc-dev-001"
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
    while True:
      moisture = random.choice([True, False])
      if moisture:
        myDeviceShadow.shadowUpdate('{"state":{"reported":{"moisture":"okay"}}}', myShadowUpdateCallback, 5)
      else:
        myDeviceShadow.shadowUpdate('{"state":{"reported":{"moisture":"low"}}}', myShadowUpdateCallback, 5)
      time.sleep(60)