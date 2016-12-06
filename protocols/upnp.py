# -*- coding: utf-8 -*-
"""This module provides the protocols payload formats and parsre
For UPnP/SSDP protocols:
    - http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.0-20080424.pdf
    - http://upnp.org/specs/arch/UPnP-arch-DeviceArchitecture-v1.1.pdf
"""

__author__ = 'douglasvinter'
__version__ = '0.1'

import os
import re
import platform
from networking import get_host_address, UdpPackage

MULTICAST_GROUP = '239.255.255.250'
MULTICAST_PORT = 1900
MULTICAST_TTL = 4
M_SEARCH = ['M-SEARCH * HTTP/1.1', 'HOST: 239.255.255.250:1900',
            'MAN: "ssdp:discover"', 'ST: {st}', 'MX: {mx}', 'USER-AGENT: {ua}', '', '']
ANSWER_TARGET = ['HTTP/1.1 200 OK', 'CACHE-CONTROL: max-age=1800', 'EXT:',
                 'LOCATION: http://{my_addr}', 'SERVER: {system_name}',
                 'ST: {search_target}', 'USN: {server_usn}', '', '']


def m_search(search_target, max_wait, user_agent):
    """

    :param search_target: Search tag you desire to send i.e ssdp:all or upnp:rootdevice
    :param max_wait: The wait for the expected UPnP version (generally all answer if <= 5)
    :param user_agent: HTTP like browser agent, or any of your preference.
    :return str: UPnP M-SEARCH message or empty string
    """
    msearch = ""
    if is_valid_search_target(search_target) and is_valid_max_wait(max_wait):
        msearch = "\r\n".join(M_SEARCH).format(st=search_target, mx=max_wait, ua=user_agent)
    return msearch


def answer(answer_type, search_target, server_identifier):
    """Builds the answer payload if a valid search for this target was readed
    on the multicast group

    Args:
        :param answer_type: service or device
        :param search_target: The search target (ST) flag you received from the socket
        :param server_identifier: For service you must answer the USN for the registered service
                                  For a device you should answer uuid:VALID_UUID

    :return str: UPnP HTTP 200 answer if correct parameters were provided
    """
    payload = ''
    active_adress = get_host_address()
    system_name = platform.system() + ' ' + platform.release() + ' / ' + os.name.upper()
    if answer_type.lower() == 'service':
        payload = "\r\n".join(ANSWER_TARGET).format(my_addr=active_adress, sys_name=system_name,
                                                    search_target=search_target, server_usn=server_identifier)
    elif answer_type.lower() == 'device':
        payload = "\r\n".join(ANSWER_TARGET).format(my_addr=active_adress, sys_name=system_name,
                                                    search_target=search_target, server_usn=server_identifier)
    return payload


def is_valid_max_wait(mx):
    """ Maximum Wait time

    Arguments:
        :param mx: Integer

    Note:
        UPnP 1.0 - MX should be between 1 and 120
        UPnP 1.1 - MX should be between 1 and 5
    """
    if 120 >= mx >= 1 or \
       5 >= mx >= 1:
        return True
    else:
        return False


def is_valid_search_target(search_target):
    """Validates UPNP search target parameter

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
    if search_target in ('ssdp:all', 'upnp:rootdevice') or \
            (search_target.startswith('urn:') and search_target.count(':') == 4) or \
            (search_target.startswith('usn:') and search_target.count(':') == 4) or \
            (search_target.startswith('uuid:') and 36 >= len(search_target[5:]) >= 32):
        return True
    else:
        return False


def parse(response):
    """Simple HTTP-U parser

    Args:
        :param response: networking.UdpPackage parsed payload
    """
    data = {}
    if not isinstance(response, UdpPackage):
        return {}
    if response.data and response.host and response.port:
        # Parse HTTP Headers by Key/Value
        data = dict(re.findall(r"(?P<name>.*?): (?P<value>.*?)\r\n", response.data))
        data = dict((k.lower(), v) for k, v in data.iteritems())
        # Gets the device/service UUID
        if 'usn' in data.keys() and ':' in data['usn']:
            key, value = data['usn'].split(':')[0:2]
            data.update({key: value})
        data.update({'sender': [response.host, response.port]})
    return data
