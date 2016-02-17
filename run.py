"""IoT Framework StartUp

Note:
    This will exist for development purposes only, in the future I plan 
    to change this whole set of signals and shut-downs semaphore to the ContextManager.
    Also verifying which OS type this framework is running for better underlying abstraction
    i.e BSD/win32/linux
"""


__author__ = 'douglasvinter'

import sys
import signal
import logging
from core.manager import ContextManager


# Logging for debbug
logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s] %(name)-15s %(levelname)-8s: %(message)s',
                    datefmt='%m/%d %H:%M:%S')

def signal_handler(signal=0, frame=0):
    ContextManager().get_instance().shutdown()

if __name__ == '__main__':
    app = ContextManager()
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
