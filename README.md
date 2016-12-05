# Simple Network Framework

Open Source project for network discovery protocols.

- Why not twisted, Tornado and etc?
    * This framework purpose is to be lightweight and use the minimum external dependencies as possible

- Protocols planned for implementation:
    * UPnP / SSDP - Done
    * mDNS - TODO
    * SLP - TODO

#SSDP Discovery


Network discovery with SSDPDaemon running

    Douglass-MacBook-Pro:simple-iot-framework dbranco$ python
    Python 2.7.10 (default, Jul 30 2016, 18:31:42)
    [GCC 4.2.1 Compatible Apple LLVM 8.0.0 (clang-800.0.34)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    >>> from protocols.discovery import SSDPDaemon
    >>> endpoint = SSDPDaemon()
    >>> endpoint.start()
    [11/30 19:57:11] SSDP Daemon     INFO    : UPnP server and client is running
    >>> endpoint.add_m_search('ssdp:all')
    True
    >>>
    [11/30 19:57:51] SSDP Daemon     DEBUG   : Received:
    {'host': '239.255.255.250:1900', 'sender': ['10.35.96.140', 62811], 'st': 'urn:dial-multiscreen-org:service:dial:1', 'man': '"ssdp:discover"', 'mx': '1', 'user-agent': 'Google Chrome/54.0.2840.98 Mac OS X'}
    >>> [11/30 19:57:52] SSDP Daemon     DEBUG   : Received:
    {'host': '239.255.255.250:1900', 'sender': ['10.35.96.140', 62811], 'st': 'urn:dial-multiscreen-org:service:dial:1', 'man': '"ssdp:discover"', 'mx': '1', 'user-agent': 'Google Chrome/54.0.2840.98 Mac OS X'}
    [11/30 19:57:53] SSDP Daemon     DEBUG   : Received:
    {'host': '239.255.255.250:1900', 'sender': ['10.35.96.140', 62811], 'st': 'urn:dial-multiscreen-org:service:dial:1', 'man': '"ssdp:discover"', 'mx': '1', 'user-agent': 'Google Chrome/54.0.2840.98 Mac OS X'}
    [11/30 19:57:54] SSDP Daemon     DEBUG   : Received:
    {'host': '239.255.255.250:1900', 'sender': ['10.35.96.140', 62811], 'st': 'urn:dial-multiscreen-org:service:dial:1', 'man': '"ssdp:discover"', 'mx': '1', 'user-agent': 'Google Chrome/54.0.2840.98 Mac OS X'}
    [11/30 19:58:52] SSDP Daemon     DEBUG   : Sending data for target 239.255.255.250:1900:
    M-SEARCH * HTTP/1.1
    HOST: 239.255.255.250:1900
    MAN: "ssdp:discover"
    ST: ssdp:all
    MX: 5
    USER-AGENT: Simple IoT Framework / 0.1


    [11/30 19:58:52] SSDP Daemon     DEBUG   : Received:
    {'host': '239.255.255.250:1900', 'sender': ['10.35.96.140', 1900], 'st': 'ssdp:all', 'man': '"ssdp:discover"', 'mx': '5', 'user-agent': 'Simple Network Framework / 0.1'}
    >>>
    >>> endpoint.join()
    [11/30 19:59:11] SSDP Daemon     INFO    : SSDP Daemon stopped
    [11/30 19:59:11] SSDP Daemon     DEBUG   : Closing RDWR for socket
    [11/30 19:59:11] SSDP Daemon     DEBUG   : Closing RDWR for socket
    >>>

	
