# Simple IoT Framework

Open Source project that provides a simple and lightweight python framework for Internet of Things.

This project will need a Embedded Linux hardware with 1-n cores and at least 256MB RAM for deploy.

Open Source framework that provides:
- RF sensor management (TODO) - Could not purchase any sensors..
- Bluetooth devices management/interface - Could not purchase bluetooth device..
- Network devices discovery (SSDP & bluetooth - On going) - For now SSDP only
- Messaging & Streaming (0MQ Based) - Still planning if worth it.
- IP Camera interface (TODO)
- REST API for remote management (TODO) 
- *App UI for HDMI  (atom/electron + AngularJS) - (TODO)

*Thinking on providing backend functionalities only, and develop a ionic app to manage/integrate with the REST API.

Aimed python runtime: PyPy 2.7.x /cPython 2.7.x

If you want to join this project or just give some feedbacks, be welcome to get in touch!

# MQ Integration

Not done yet.

#SSDP Discovery


Network discovery with SSDP standalone (without the framework)

	(iot)adminuser@linux:~/github_projects/iot/simple-iot-framework> python
	Python 2.7.8 (default, Sep 30 2014, 15:34:38) [GCC] on linux2
	Type "help", "copyright", "credits" or "license" for more information.
	>>> from protocols.discovery import SSDP
	>>> d = SSDP(search_target='ssdp:all', upnp_version=1.1, upnp_max_wait=5)
	>>> for device in d.m_search():
	>>>     print device
	[02/01 18:41:19] SSDP Client     DEBUG   : Sending data for target 239.255.255.250:1900:
	M-SEARCH * HTTP/1.1
	HOST: 239.255.255.250:1900
	MAN: "ssdp:discover"
	ST: ssdp:all
	MX: 5
	[02/01 18:41:19] SSDP Client     DEBUG   : {'cache-control': 'max-age=1800',
	 'location': 'http://192.168.1.202:2869/upnphost/udhisapi.dll?content=uuid:30c0fe1b-528d-4870-a0c0-73dbc2c14a10',
	 'server': 'Microsoft-Windows-NT/5.1 UPnP/1.0 UPnP-Device-Host/1.0',
	 'st': 'urn:dmc-samsung-com:device:SyncServer:1',
	 'usn': ' uuid:30c0fe1b-528d-4870-a0c0-73dbc2c14a10::urn:dmc-samsung-com:device:SyncServer:1',
	 'uuid': '30c0fe1b-528d-4870-a0c0-73dbc2c14a10'}
	[02/01 18:41:23] SSDP Client     DEBUG   : Timeout while waiting for answer: timed out {}
	[02/01 18:41:23] SSDP Client     DEBUG   : Search done
	>>>
	
