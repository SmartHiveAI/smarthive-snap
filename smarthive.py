"""
SmartHive Snap
"""
import logging
import threading
from http.server import HTTPServer

import http_helper
from http_helper import HTTPHelper
from mdns_helper import MDNSHelper
from mqtt_helper import MQTTHelper
import defines

LOGGER = logging.getLogger("SmartHive.Main")

def main():
    '''Main entry point - configures and starts - logger, mdns, provisioning check and http'''
    LOGGER.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    LOGGER.addHandler(stream_handler)
    LOGGER.info('Starting SmartHive Cloud Controller ...')
    # MDNS
    MDNSHelper()
    MDNSHelper.resolve_mdns("SmartHive-GW")
    # while True:
    #    mdns_helper.resolve_mdns("SmartHive-GW")
    #    time.sleep(10)
    # Check for provisioning status and config
    is_provisioned = http_helper.check_provisioned()
    LOGGER.info("Provisioned status: %s", is_provisioned)
    if is_provisioned is True: MQTTHelper()
    # Local http server
    local_svr = HTTPServer(("", defines.SVC_PORT), HTTPHelper)
    httpthread = threading.Thread(target=local_svr.serve_forever)
    httpthread.start()

if __name__ == "__main__":
    main()
