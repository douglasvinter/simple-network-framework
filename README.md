# Simple Network Framework

Open Source project for network discovery protocols.

- Why not twisted, Tornado and etc?
    * This framework purpose is to be lightweight and use the minimum external dependencies as possible

- Protocols planned for implementation:
    * UPnP / SSDP - Done
    * mDNS - TODO
    * SLP - TODO

#SSDP Discovery

Running with playground.py * Test & learning sample *

	douglasvinter@environment:~/github/simple-network-framework$ python playground.py 
	douglasb@linuxcit012107:~/github/simple-network-framework$ python playground.py 
	[04/20 16:43:24] SSDP Agent      INFO    : SSDP agent started!
	[04/20 16:43:24] SSDP Agent      DEBUG   : Added new M-SEARCH for target: ssdp:all
	[04/20 16:43:24] SSDP Agent      INFO    : Endpoint Flags
	[04/20 16:43:24] SSDP Agent      DEBUG   : Press Ctrl+C to quit
	[04/20 16:43:24] SSDP Agent      INFO    : ST=urn:schemas-upnp-org:service:SimpleNetworkFramework:1
	[04/20 16:43:24] SSDP Agent      INFO    : UUID=uuid:xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
	[04/20 16:43:24] SSDP Agent      INFO    : USER_AGENT=Simple Network Framework / 0.1
	[04/20 16:43:24] SSDP Agent      INFO    : UPnP server and client is running
	[04/20 17:14:40] SSDP Agent      DEBUG   : sending M-SEARCH messages...
	[04/20 17:14:40] SSDP Agent      DEBUG   : Sending data for target 239.255.255.250:1900:
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Sending M-SEARCH: 
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.19.100:54899
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Parsed payload:
	{'host': '239.255.255.250:1900', 'sender': ['172.16.19.100', 54899], 'st': 'ssdp:all', 'man': '"ssdp:discover"', 'mx': '5', 'user-agent': 'Simple Network Framework / 0.1'}
	[04/20 17:14:40] SSDP Agent      DEBUG   : get_host_address()->172.16.19.100-172.16.19.100
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	HTTP/1.1 200 OK
	Location: http://172.16.47.72:1850/
	Cache-Control: max-age=1800
	Server: Linux/i686 UPnP/1.0 DLNADOC/1.50 Platinum/1.0.3.0
	USN: uuid:d093c502-b0ca-e13c-2f0a-609cbefe3080::urn:lge-com:device:SSTDevice:1
	ST: urn:lge-com:device:SSTDevice:1
	EXT: 
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.47.72:1900
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	HTTP/1.1 200 OK
	CACHE-CONTROL: max-age=1800
	LOCATION: http://172.16.47.68:7676/smp_11_
	ST: urn:schemas-upnp-org:service:ConnectionManager:1
	SERVER: SHP, UPnP/1.0, Samsung UPnP SDK/1.0
	USN: uuid:0c845881-00d2-1000-9130-ccb11a7ca518::urn:schemas-upnp-org:service:ConnectionManager:1
	EXT: 
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.47.68:1900

	^C[04/20 16:46:29] SSDP Agent      INFO    : SSDP Daemon stopped
	[04/20 16:46:29] SSDP Agent      DEBUG   : Closing RDWR for socket
	[04/20 16:46:29] SSDP Agent      DEBUG   : Closing RDWR for socket
	[04/20 16:46:29] SSDP Agent      DEBUG   : Bye!
	douglasvinter@environment:~/github/simple-network-framework$ 


Network discovery with SSDPDaemon running

    douglasvinter@environment:~/github/simple-network-framework$ python
    Python 2.7.12 (default, Nov 19 2016, 06:48:10) 
	[GCC 5.4.0 20160609] on linux2
	Type "help", "copyright", "credits" or "license" for more information.
	>>> from protocols.discovery import SSDPDaemon
	>>> endpoint = SSDPDaemon()
	>>> endpoint.add_m_search('ssdp:all')
	[04/20 17:05:58] SSDP Agent      DEBUG   : Added new M-SEARCH for target: ssdp:all
	True
	>>> endpoint.start()	
	[04/20 17:14:30] SSDP Agent      INFO    : SSDP agent started!
	[04/20 17:14:30] SSDP Agent      DEBUG   : Added new M-SEARCH for target: ssdp:all
	[04/20 17:14:30] SSDP Agent      INFO    : Endpoint Flags
	[04/20 17:14:30] SSDP Agent      DEBUG   : Press Ctrl+C to quit
	[04/20 17:14:30] SSDP Agent      INFO    : ST=urn:schemas-upnp-org:service:SimpleNetworkFramework:1
	[04/20 17:14:30] SSDP Agent      INFO    : UUID=uuid:xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
	[04/20 17:14:30] SSDP Agent      INFO    : USER_AGENT=Simple Network Framework / 0.1
	[04/20 17:14:30] SSDP Agent      INFO    : UPnP server and client is running
	[04/20 17:14:40] SSDP Agent      DEBUG   : sending M-SEARCH messages...
	[04/20 17:14:40] SSDP Agent      DEBUG   : Sending data for target 239.255.255.250:1900:
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Sending M-SEARCH: 
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	USER-AGENT: Simple Network Framework / 0.1
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.19.100:54899
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Parsed payload:
	{'host': '239.255.255.250:1900', 'sender': ['172.16.19.100', 54899], 'st': 'ssdp:all', 'man': '"ssdp:discover"', 'mx': '5', 'user-agent': 'Simple Network Framework / 0.1'}
	[04/20 17:14:40] SSDP Agent      DEBUG   : get_host_address()->172.16.19.100-172.16.19.100
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	HTTP/1.1 200 OK
	Location: http://172.16.47.72:1850/
	Cache-Control: max-age=1800
	Server: Linux/i686 UPnP/1.0 DLNADOC/1.50 Platinum/1.0.3.0
	USN: uuid:d093c502-b0ca-e13c-2f0a-609cbefe3080::urn:lge-com:device:SSTDevice:1
	ST: urn:lge-com:device:SSTDevice:1
	EXT: 
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.47.72:1900
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	HTTP/1.1 200 OK
	CACHE-CONTROL: max-age=1800
	LOCATION: http://172.16.47.68:7676/smp_11_
	ST: urn:schemas-upnp-org:service:ConnectionManager:1
	SERVER: SHP, UPnP/1.0, Samsung UPnP SDK/1.0
	USN: uuid:0c845881-00d2-1000-9130-ccb11a7ca518::urn:schemas-upnp-org:service:ConnectionManager:1
	EXT: 
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.47.68:1900
	
	[04/20 17:14:40] SSDP Agent      DEBUG   : Received MCAST:
	
	******* PACKAGE DATA *******
	
	HTTP/1.1 200 OK
	CACHE-CONTROL: max-age=1800
	LOCATION: http://172.16.47.60:52323/dmr.xml
	ST: urn:schemas-upnp-org:service:ConnectionManager:1
	SERVER: Linux/2.6 UPnP/1.0 KDL-32W605A/1.7
	USN: uuid:00000000-0000-1010-8000-d8d43c469f0b::urn:schemas-upnp-org:service:ConnectionManager:1
	X-AV-Physical-Unit-Info: pa="BRAVIA KDL-32W605A";
	X-AV-Server-Info: av=5.0; cn="Sony Corporation"; mn="BRAVIA KDL-32W605A"; mv="1.7";
	EXT: 
	
	
	******* END OF PACKAGE DATA *******
	FROM: 172.16.47.60:1900

	^C[04/20 17:15:34] SSDP Agent      INFO    : SSDP Daemon stopped
	[04/20 17:15:34] SSDP Agent      DEBUG   : Closing RDWR for socket
	[04/20 17:15:34] SSDP Agent      DEBUG   : Closing RDWR for socket
	[04/20 17:15:34] SSDP Agent      DEBUG   : Bye!
	douglasvinter@environment:~/github/simple-network-framework$

	
