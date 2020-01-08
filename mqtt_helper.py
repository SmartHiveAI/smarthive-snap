'''Pub Sub Helper with AWS MQTT'''
import json
import logging
import threading
import AWSIoTPythonSDK
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import defines
import http_helper
from http_helper import HTTPConnPoolMgr

LOGGER = logging.getLogger("SmartHive.MQTT")

class MQTTHelper:
    '''Helper class to receive commands over MQTT, pass through to Mesh and respond back to the cloud gateway'''
    def __init__(self):
        LOGGER.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        LOGGER.addHandler(stream_handler)

        self.conn_mgr = HTTPConnPoolMgr()

        LOGGER.info("MQTT config - ClientId: %s, Topic: %s", defines.CLIENT_ID, defines.TOPIC)
        self.mqtt_client = None
        self.mqtt_client = AWSIoTMQTTClient(defines.CLIENT_ID)
        self.mqtt_client.configureEndpoint(http_helper.MQTT_HOST, http_helper.MQTT_PORT)
        self.mqtt_client.configureCredentials(defines.ROOT_CA, defines.PRIVATE_KEY, defines.CERT_FILE)
        self.mqtt_client.configureAutoReconnectBackoffTime(1, 60, 10) # 1 - 60 seconds backoff, 10 sec stable reset
        self.mqtt_client.configureOfflinePublishQueueing(100, AWSIoTPythonSDK.MQTTLib.DROP_OLDEST) # queue 100 requests
        self.mqtt_client.configureDrainingFrequency(2)  # Draining: 2 Hz
        self.mqtt_client.configureConnectDisconnectTimeout(10)  # 10 sec
        self.mqtt_client.configureMQTTOperationTimeout(5)  # 5 sec
        self.mqtt_client.enableMetricsCollection()
        self.mqtt_client.onOffline = self.onOffline_callback
        self.mqtt_client.onOnline = self.onOnline_callback
        self.mqtt_client.connect(60)
        self.mqtt_client.subscribe(defines.TOPIC, 1, self.mqtt_callback)
        #self.heartbeat()
        # time.sleep(2)

    def onOffline_callback(self):
        LOGGER.info("<------MQTT OFFLINE------>")

    def onOnline_callback(self):
        LOGGER.info("<------MQTT ONLINE------>")

    def mqtt_publish(self, topic, message):
        '''Send data over MQTT'''
        message_str = json.dumps(message)
        self.mqtt_client.publish(defines.TOPIC, message_str, 1)
        LOGGER.info("Published topic %s: %s", defines.TOPIC, message_str)

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
                    if mesh_response is None: mesh_response = {}
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
            self.mqtt_publish(defines.TOPIC, payload)
            threading.Timer(900, self.heartbeat).start()
        except Exception as e:
            LOGGER.info('Failed to send heartbeat: %s', str(e))
