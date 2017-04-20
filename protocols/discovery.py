# -*- coding: utf-8 -*-
"""Implementation of network discovery protocols
Done:
    - UPnP/SSDP
To-do:
    - SLP
    - mDNS
"""

__author__ = 'douglasvinter'
__version__ = '0.1'

import upnp
import time
import Queue
import logging
import threading
from networking import DatagramSocket, SocketSelector, \
    MulticastException, UnicastException, get_host_address

# Logging for debugging
logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s] %(name)-15s %(levelname)-8s: %(message)s',
                    datefmt='%m/%d %H:%M:%S')


class SSDPException(Exception):
    """Exception base class for SSDP protocol errors

    Note:
        Will only be raised only when you instantiate this class with wrong UPnP
        parameters.
    """
    pass


class SSDP(object):
    """Simple Service Discovery Protocol for services and devices.

    See full explanation at class SSDPDaemon
    """

    USER_AGENT = 'Simple Network Framework / 0.1'

    def __init__(self, logger_name='SSDP Client'):
        """Creates an SSDP Client to send messages as per your implementation

        :param logger_name: String logger name, default: 'SSDP Client'.
        """

        self.client = DatagramSocket(socket_type=DatagramSocket.CLIENT,
                                     implemented_protocol=SSDP.__class__.__name__,
                                     logger_name=logger_name,
                                     group=upnp.MULTICAST_GROUP,
                                     port=upnp.MULTICAST_PORT,
                                     ttl=upnp.MULTICAST_TTL)

    def __del__(self):
        """Destructor method

        Note:
            Not closing sockets may lead to a socket backlog problem on your host/embedded device
        """
        self.client.destroy()

    def send(self, search_target,  max_wait=5, user_agent=None):
        """ Builds SSDP M-SEARCH payload and send to the multicast group

        Args:
            :param search_target: String containing ST tag according to UPnP documentation.
            :param max_wait: max wait / MX parameter for UPnP protocol, default is 5, which makes
                both UPnP 1.0 and 1.1 reply (most cases)
            :param user_agent: HTTP like browser agent, or any of your preference.
        :return bool:
        """
        if user_agent is None:
            user_agent = SSDPDaemon.USER_AGENT
        try:
            if upnp.is_valid_search_target(search_target) and upnp.is_valid_max_wait(max_wait):
                msg = upnp.m_search(search_target, max_wait, user_agent)
                self.client.send_multicast(msg)
                return True
        except MulticastException as mcast_error:
            self.logging.error("Error sending multicast:\n{}".format(mcast_error))
        return False

    def receive(self):
        """Tries to receive data, if any.

        :return: dict
        """
        payload = {}
        try:
            payload = self.client.recv_dgram()
            payload = upnp.parse(payload)
        except UnicastException as uni_error:
            self.logging.error("Error receiving unicast:\n{}".format(uni_error))
        return payload


class SSDPDaemon(threading.Thread):
    """Simple Service Discovery Protocol for services and devices.

    This protocol basically sends a multicast UDP package containing
    a HTTP based SOAP message for the group 239.255.255.250 and waits
    for a unicast HTTP SOAP message response from the device/service
    if any of the searched over the net answers.

    Note:
        Its pretty common to send a UPnP 1.1 protocol scan and receive
        an UPnP 1.0 response, since they're pretty  much equal.
        *Only M - SEARCH and NOTIFY will be available for now,
        The service wont advertise its presence on the LAN.

    The searchTarget supports a series of payload

    Flow:
                            Multicast Group(239.255.255.250)
                                              |L|
        ______________________                |A|     ____________________
        |    Control Point    |    Multicast  |N|     |  root device      |
        |                     |     (request) | |     | ---------------   |
        |                     |===============|=|====>| |device         | |
        |                     |               | |     | | ------------- | |
        |                     |<--------------|-|-----| | |   service | | |
        |                     |   Unicast     | |     | | |___________| | |
        |                     |    (response) | |     | |_______________| |
        |_____________________|                       |___________________|
    """

    

    def add_m_search(self, search_target,  max_wait=5):
        """ Builds SSDP M-SEARCH payload and add to search strings, won't accept the same search_target

        Args:
            :param search_target: String containing ST tag according to UPnP documentation.
            :param max_wait: max wait / MX parameter for UPnP protocol, default is 5, which makes
                both UPnP 1.0 and 1.1 reply (most cases)
        :return bool:
        """

        for i in xrange(len(self._search_strings)):
            if self._search_strings[i].find(search_target) > -1:
                self.logging.info("ST: {} already registered, not added.".format(search_target))
                return False
        if upnp.is_valid_search_target(search_target) and upnp.is_valid_max_wait(max_wait):
            self._search_strings.append(upnp.m_search(search_target, max_wait, self.user_agent))
            self.logging.debug('Added new M-SEARCH for target: {}'.format(search_target))
            return True
        return False

    def remove_m_search(self, search_target):
        """Removes all search parameters that contains the informed string

        Args:
            :param search_target: search target string to be removed from list
        """
        idx = []
        for i in xrange(len(self._search_strings)):
            if self._search_strings[i].find(search_target) > -1:
                idx.append(i)
                self.logging.debug('Removed M-SEARCH for target: {}'.format(self._search_strings[i]))
        self._search_strings = [v for k, v in enumerate(self._search_strings) if k not in idx]



    def __init__(self, server_usn='urn:schemas-upnp-org:service:SimpleNetworkFramework:1',
                 server_uuid='uuid:xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx',
                 user_agent= 'Simple Network Framework / 0.1', m_search_timeout=100.0,
                 logger_name='SSDP Agent', monitoring=False):
        """Creates an SSDPDaemon agent to keep sending and receiving SSDP messages

        Args:
            :param server_usn: register your service tag to be found on network
            :param server_uuid: register your device tag to be found on network
            :param m_search_timeout: timeout to send m search strings in seconds
            :param logger_name: String logger name, default: 'SSDP Daemon'.
            :param monitoring: Change this flag to true if you want all the data to be in the Queue -
                server_out_q

        Note:
            The client will NOT start sending M-SEARCH strings unless you call the method
            add_m_search first.

        Raises:
            JoinGroupError - Socket level errors for multicast will be raised on the instantiation
            SSDPException - Wrong parameters will result on a exception
        """
        self._search_strings = []
        # Queue to get all responses and parse to your component
        self.client_out_q = Queue.Queue()
        # Note the server out q will only populate if monitoring is set
        self.server_out_q = Queue.Queue()
        self.monitoring = monitoring
        # Flags for upnp:rootdevice and ssdp:all
        self.server_usn = server_usn
        self.server_uuid = server_uuid
        self.user_agent = user_agent
        self.logging = logging.getLogger(logger_name)
        # Event M-SEARCH timeout in seconds
        assert (type(m_search_timeout) in [float, int]), \
            "Invalid type periodic_search_time {}".format(m_search_timeout)
        self.task_interval = m_search_timeout
        # Main loop
        self.__is_running = True
        self.main_loop = lambda: self.__is_running
        # Unicast socket
        self.client = DatagramSocket(socket_type=DatagramSocket.CLIENT,
                                     implemented_protocol=SSDPDaemon.__class__.__name__,
                                     logger_name=logger_name,
                                     group=upnp.MULTICAST_GROUP,
                                     port=upnp.MULTICAST_PORT,
                                     ttl=upnp.MULTICAST_TTL)
        # Multicast socket, listener only
        self.server = DatagramSocket(socket_type=DatagramSocket.SERVER,
                                     implemented_protocol=SSDPDaemon.__class__.__name__,
                                     logger_name=logger_name,
                                     group=upnp.MULTICAST_GROUP,
                                     port=upnp.MULTICAST_PORT,
                                     ttl=upnp.MULTICAST_TTL)
        threading.Thread.__init__(self)
        self.daemon = True
        
    def run(self):
        """Overrides threading.Thread.run method
        basic daemon routine is to keep sending / receiving data

        Use methods: add_m_search and remove_m_search to manage this daemon
        """
        self.logging.info('SSDP agent started!')
        self.logging.info('Endpoint Flags')
        self.logging.info('ST={}'.format(self.server_usn))
        self.logging.info('UUID={}'.format(self.server_uuid))
        self.logging.info('USER_AGENT={}'.format(self.user_agent))
        event_time = time.time()
        self.logging.info("UPnP server and client is running")
        while self.main_loop():
            for sock in SocketSelector.select_protocol(SSDPDaemon.__class__.__name__):
                if self.client.transport == sock:
                    self.handle_client()
                elif self.server.transport == sock:
                    self.handle_server()
            # Can be done via threading.Timer as well
            # But here we`ve a easy way to control the timer
            if (time.time() - event_time) >= self.task_interval > 0:
                self.logging.debug('sending M-SEARCH messages...')
                self.m_search()
                event_time = time.time()

    def __del__(self):
        """Destructor method

        Note:
            Not closing sockets may lead to a socket backlog problem on your host/embedded device
        """
        self.client.destroy()
        self.server.destroy()

    def handle_server(self):
        """Handles multicasts messages on the group

        This will simply reply when receives the registered tag, ssdp:all and upnp:rootdevice
        """
        msg = ''
        payload = self.server.recv_dgram()
        payload = upnp.parse(payload)
        self.logging.debug('Parsed payload:\n{}'.format(payload))
        if self.monitoring:
            self.server_out_q.put_nowait(payload)
        self.logging.debug('get_host_address()->{}-{}'.format(get_host_address(), payload['sender'][0]))
        if payload['sender'][0] != get_host_address():
            try:
                upnp.is_valid_search_target(payload['st'])
            except SSDPException:
                # Invalid flag will be log as a warning
                self.logging.warning('Detected a message out of standard from: {}:{}'
                                     .format(payload['sender'][0], payload['sender'][1]))
            else:
                if payload['st'] == self.server_usn or payload['st'] == 'ssdp:all':
                    self.client.send_unicast(upnp.answer('device', payload['st'], self.server_usn),
                                             *payload['sender'])
                elif payload['st'] == self.server_uuid or payload['st'] == 'upnp:rootdevice':
                    self.client.send_unicast(upnp.answer('device', payload['st'], self.server_uuid),
                                             *payload['sender'])

    def handle_client(self):
        """Handles unicast received from a UPnP service/device"""
        try:
            payload = self.client.recv_dgram()
            payload = upnp.parse(payload)
            if len(payload.keys()) > 1:
                self.client_out_q.put_nowait(payload)
            # Will add any sort of network response on this group
            elif self.monitoring:
                self.client_out_q.put_nowait(payload)
        except UnicastException:
            pass

    def m_search(self):
        """Sends m-search strings registered on search strings"""
        # avoid atomic operation problems on remove_m_search method
        search_strings = self._search_strings
        for payload in search_strings:
            try:
                self.client.send_multicast(payload)
                self.logging.debug('Sending M-SEARCH: \n{}'.format(payload))
            except MulticastException:
                pass

    def join(self, timeout=None):
        """Wrapper of threading.Thread.join method"""
        self.__is_running = False
        threading.Thread.join(self, timeout=timeout)
        self.logging.info("SSDP Daemon stopped")
        self.client.destroy()
        self.server.destroy()
        # Call destructor
        del self
