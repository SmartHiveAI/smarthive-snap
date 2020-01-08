'''mDNS helper functions for discovery and registration'''
import socket
import logging
from zeroconf import ServiceInfo, Zeroconf, DNSAddress
import defines

LOGGER = logging.getLogger("SmartHive.MDNS")

class MDNSHelper:
    '''MDNS management ... mainly looking for mesh gateway node'''
    ip_addr = ""
    zeroconf = Zeroconf()
    info = None

    def __init__(self):
        LOGGER.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        LOGGER.addHandler(stream_handler)
        self.get_local_address()
        self.info = ServiceInfo("_http._tcp.local.", defines.SVC_NAME + "._http._tcp.local.", socket.inet_aton(self.ip_addr), defines.SVC_PORT, 0, 0, {"version": "0.1"}, defines.SVC_NAME + ".local.")
        self.zeroconf.register_service(self.info)
        LOGGER.info("Local mDNS on domain: %s", defines.SVC_NAME)

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
