"""IoT Framework StartUp
"""


__author__ = 'douglasvinter'

import sys
import signal
import logging
from core.manager import AppManager


# Logging for debbug
logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s] %(name)-15s %(levelname)-8s: %(message)s',
                    datefmt='%m/%d %H:%M:%S')

def signal_handler(signal=0, frame=0):
    AppManager().get_instance().shutdown()

if __name__ == '__main__':
    app = AppManager()
    app.daemon = True
    app.start()
    if sys.platform.startswith('win'):
        try:
            while app.manager_event.isSet(): pass
        except KeyboardInterrupt:
            signal_handler()
    else:
        signal.signal(signal.SIGINT, signal_handler)
        app.logging.info('Press Ctrl+C to stop')
        signal.pause()
