# -*- coding: utf-8 -*-
"""Play ground for testing & learning
"""

__author__ = 'douglasvinter'
__version__ = '0.1'

import sys
import time
import signal
from protocols.discovery import SSDPDaemon

endpoint = SSDPDaemon()
endpoint.start()
endpoint.add_m_search('ssdp:all', 5)

def signal_handler(signal, frame):
        endpoint.join()
        endpoint.logging.debug('Bye!')
        time.sleep(1)
        sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)
endpoint.logging.debug('Press Ctrl+C to quit')
signal.pause()
