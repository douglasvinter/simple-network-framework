# -*- coding: utf-8 -*-
"""Network discovery protocols
Discovery for network devices and services, this module contains
the implementation of UPnP/SSDP protocols, that can be verified on:
    For UPnP 1.0:
        - http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.0-20080424.pdf
    For UPnP 1.1:
        - http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
"""


__author__ = 'douglasvinter'
__version__ = '0.1'


import re
import pprint
import logging
from time import time
from .multicast import Multicast

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


class SSDP(Multicast):
    """Simple Service Discovery Protocol for services and devices.

    This protocol basically sends a multicast UDP package containing
    a HTTP based SOAP message for the group 239.255.255.250 and waits
    for a unicast HTTP SOAP message response from the device/service
    if any of the searched over the net answers.

    Note:
        Its pretty common to send a UPnP 1.1 protocol scan and receive
        an UPnP 1.0 response, since they're pretty  much equal.

    Note 2:
        For now there's no plans to implement NOTIFY / ADIVERTISE,
        Only M - SEARCH will be available for now.

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

    _upnp_version = 0
    _search_target = ''
    _maximum_time = 0
    # Created constants in case someone wants to
    # override the __init__ of this class.
    UPNP_MULTICAST_GROUP = '239.255.255.250'
    UPNP_MULTICAST_PORT = 1900
    UPNP_MULTICAST_TTL = 4

    @property
    def upnp_version(self):
        """int(upnp) returns upnp protocol version"""
        return SSDP._upnp_version

    @upnp_version.setter
    def upnp_version(self, version):
        """Sets UPnP protocol version

        Args:
            :param version - expects real number 1.0 or 1.1
        """
        if version not in [1.0, 1.1]:
            raise SSDPException('UPnP valid versions are: 1.0 and 1.1')
        SSDP._upnp_version = version

    @property
    def search_target(self):
        """str(st) returns search target string"""
        return SSDP._search_target

    @search_target.setter
    def search_target(self, search_target):
        """UPnP search Target

        Flags:
            ssdp:all
                Search for all devices and services.
            upnp:rootdevice
                Search for root devices only.
            uuid:device-UUID
                Search for a particular device. Device UUID specified by UPnP vendor.
            urn:schemas-upnp-org:device:deviceType:v
                Search for any device of this type. Device type and version defined by
                UPnP Forum working committee.
            urn:schemas-upnp-org:service:serviceType:v
                Search for any service of this type. Service type and version defined by
                UPnP Forum working committee.
            urn:domain-name:device:deviceType:v
                Search for any device of this type. Domain name, device type
                and version defined by UPnP vendor. Period characters in the domain name
                must be replaced with hyphens in accordance with RFC 2141.
            urn:domain-name:service:serviceType:v
                Search for any service of this type. Domain name, service type
                and version defined by UPnP vendor. Period characters in the domain name
                must be replaced with hyphens in accordance with RFC 2141.
        """
        if search_target in ('ssdp:all', 'upnp:rootdevice'):
            SSDP._search_target = search_target
        elif search_target.startswith('usn') and search_target.count(':') == 4:
            SSDP._search_target = search_target
        # Between 32 (with dash) and 36 characters (without dash)
        elif search_target.startswith('uuid') and 36 >= len(search_target[5:]) >= 32:
            SSDP._search_target = search_target
        else:
            raise SSDPException('Invalid Search Target pattern: {}'.format(search_target))

    @property
    def upnp_max_wait(self):
        """int(mx) returns maximum wait time"""
        return SSDP._maximum_time

    @upnp_max_wait.setter
    def upnp_max_wait(self, max_wait):
        """ Maximum Wait time

        Arguments:
            :param mx
                For UPnP 1.0 - MX should be between 1 and 120
                For UPnP 1.1 - MX should be between 1 and 5
        """
        if self.upnp_version == 1.0 and 120 >= max_wait >= 1:
            SSDP._maximum_time = max_wait
        elif self.upnp_version == 1.1 and 5 >= max_wait >= 1:
            SSDP._maximum_time = max_wait
        else:
            raise SSDPException('Invalid MX parameter {} for UPnP {}' \
                .format(max_wait, self.upnp_version))

    @property
    def msearch_payload(self):
        """ Builds SSDP M-SEARCH payload"""
        msearch = "\r\n".join(['M-SEARCH * HTTP/1.1', 'HOST: 239.255.255.250:1900', \
            'MAN: "ssdp:discover"', 'ST: {st}', 'MX: {mx}', '', ''])
        return msearch.format(st=self.search_target, mx=self.upnp_max_wait)

    def __init__(self, search_target, upnp_version, upnp_max_wait=0, \
        logger_name='SSDP Client'):
        """Creates an SSDP instance, which is a subclass of Multicast

        Args:
            :param search_target - String containing ST tag according to UPnP documentation.
            :param upnp_version - float protocol version, 1.0 or 1.1
            :param upnp_max_wait - max wait / MX parameter for UPnP protocol,
                if omitted will use the maximum for each protocol version
            :param verbose - bool to set verbose on socket operations.
            :param logger_name - String logger name, default: 'SSDP Client'.

        Raises:
            JoinGroupError - Socket level errors for multicast will be raised on the instantiation
            SSDPException - Wrong parameters will result on a exception
        """
        self.upnp_version = float(upnp_version)
        self.search_target = search_target
        upnp_max_wait = int(upnp_max_wait)
        if upnp_max_wait <= 0:
            self.upnp_max_wait = 120 if upnp_version == 1.0 else 3
        else:
            self.upnp_max_wait = upnp_max_wait
        Multicast.__init__(self, logger_name=logger_name)
        # Multicast group for SSDP
        self.group = SSDP.UPNP_MULTICAST_GROUP
        # Multicast port for SSDP
        self.port = SSDP.UPNP_MULTICAST_PORT
        # Multicast TTL, may hop over subnets
        self.sock_ttl = SSDP.UPNP_MULTICAST_TTL
        # Up to you, doesn't really matter since we're using a generator
        # based mechanism to return data
        self.sock_timeout = 1
        # Builds the protocol
        self.build_protocol()
        # Membership to SSDP multicast channel
        # NOTE: The multicast class already does the fall-back in case of errors
        # while joining on a group, but we won't catch it as you may want to do your own fall-back
        self.join_group()

    def __enter__(self):
        return self

    def __exit__(self):
        if self.is_connected:
            self.destroy()

    def __del__(self):
        """Closes socket, if implementer forgets it open

        Note:
            Not closing sockets may lead to a socket backlog problem on your host/embedded device
        """
        self.destroy()

    def m_search(self, max_search_time=0):
        """Generator method for network responses, the call will multicast the M - SEARCH message
        and wait for responses until the MX (max wait + 2 seconds) expires.

        Args:
            :param max_search_time - total time to keep searching in seconds,
                if committed, we'll use the MX parameter + 2 seconds

        Note:
            If there's a network error this generator will raise the exception and stop.
            (is_connected will return false due to the exception mechanism).

        Raises:
            Both exceptions are implemented on Multicast class.
            MulticastException - Raises if any socket level error occurs while sending data.
            UnicastResponseError - Raises if any socket level error occurs while receiving data.
        """
        # Note: The socket will keep listening if no network errors occurs.
        # Its the implementer decision to keep this alive or not.
        self.mcast_dgram(self.msearch_payload)
        start = time()
        max_search_time += 2 if max_search_time > 0 else self.upnp_max_wait + 2
        self.logging.debug('Starting search for {} seconds'.format(max_search_time))
        while self.is_connected and int((time() - start)) <= max_search_time:
            res = self.recv_dgram()
            upnp = {}
            if res.data and res.host and res.port:
                # Parse HTTP Headers by Key/Value
                upnp = dict(re.findall(r"(?P<name>.*?): (?P<value>.*?)\r\n", res.data))
                upnp = dict((k.lower(), v) for k, v in upnp.iteritems())
                # Gets the device/service UUID
                if 'usn' in upnp.keys() and ':' in upnp['usn']:
                    key, value = upnp['usn'].split(':')[0:2]
                    upnp.update({key : value})
                self.logging.debug(pprint.pformat(upnp))
            yield upnp
        self.logging.debug('Search done')
