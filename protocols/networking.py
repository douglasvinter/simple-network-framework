# -*- coding: utf-8 -*-
"""Base UDP Multicast.
Relaying only on pure Python socket API
"""

__author__ = 'douglasvinter'
__version__ = '0.1'


import socket
import struct
import select
import netifaces
from logging import getLogger
from collections import namedtuple

# udp_pkg used to return datagram status
# Class-like declaration
UdpPackage = namedtuple('udp_pkg', ('data', 'host', 'port'))


class ProtocolError(Exception):
    """ Exception base class for datagram network errors

    Args:
        msg (str): Human readable string describing the exception.

    Attributes:
        msg (str): Human readable string describing the exception.
    """

    def __init__(self, msg):
        super(ProtocolError, self).__init__(msg)


class MulticastException(ProtocolError):
    """ Exception subclass for multicast error"""
    pass

class UnicastException(ProtocolError):
    """ Exception subclass for unicast error"""
    pass


class JoinGroupError(ProtocolError):
    """ Exception subclass for join group operation"""
    pass


class NetworkConfigurationError(ProtocolError):
    """ Exception subclass for network configuration errors"""
    pass


class SocketSelector(object):
    """"""

    # select.select timeout
    SOCKET_TIMEOUT = 0.1
    _instance = None
    sockets = []

    def __new__(cls, *args, **kwargs):
        """"""
        if cls._instance is None:
            cls._instance = super(SocketSelector, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    @staticmethod
    def add_handler(klaas):
        if klaas is not None:
            SocketSelector.sockets.append(klaas)

    @staticmethod
    def get_instance():
        """Gets class instance."""
        if not SocketSelector._instance:
            SocketSelector._instance = SocketSelector()
        return SocketSelector._instance

    @staticmethod
    def select_all():
        """Simple I/O selector

        Returns:
            List of ready sockets to be read
        """

        sockets = []
        socks_ready = []
        for cls in SocketSelector.get_instance().sockets:
            sockets.append(cls.transport)
        try:
            socks_ready, _, _ = select.select(sockets, [], [], SocketSelector.SOCKET_TIMEOUT)
        except (socket.error, TypeError):
            pass
        return socks_ready

    @staticmethod
    def select_protocol(protocol):
        """Simple I/O selector

        Args:
            :param protocol: Protocol name to hook up on sub classes

        Returns:
            List of ready sockets to be read
        """

        sockets = []
        socks_ready = []
        for cls in SocketSelector.get_instance().sockets:
            if cls.implemented_protocol == protocol:
                sockets.append(cls.transport)
        try:
            socks_ready, _, _ = select.select(sockets, [], [], SocketSelector.SOCKET_TIMEOUT)
        except (socket.error, TypeError):
            pass
        return socks_ready


class DatagramSocket(object):
    """A pure python Class for Networking datagram packages

    This class was based in some extent of Twisted networking mechanism but much simpler.
    It basically provides the bases of multicast enabling you to join into IGMP groups.

    You can also perform unicast using this class, you have just to avoid listening and binding
    it in the same address you wish to use your protocols.

    Note:
        If you're thinking on use this class to bind into multiple IGMP groups you've joined,
        feel free to, but check your max_memberships flag first.
        (Linux - /proc/sys/net/ipv4/igmp_max_memberships)
    """
    # Public constants
    CLIENT = 0x554e4943415354
    SERVER = 0x4d554c544943415354

    def __init__(self, socket_type, implemented_protocol, logger_name, group, port, ttl=None, recv_size=1024):
        """DatagramSocket constructor

        Args:
            :param socket_type: unicast or multicast constant value
            :param implemented_protocol: Protocol name that you're implementing
            :param logger_name: Valid logger name.
            :param group: multicast address.
            :param port: multicast port.
            :param ttl: time to live, datagram package hops.
            :param recv_size: size in bytes to be received.
                Max UDP package is 64Kb = 65536
        Note:
            Please make sure to chose the correct socket_type:
                - If you want a MUSTICAST litener ONLY, chose the socket type to be SERVER.
                - If you want a socket to send MULTICAST and UNICAST but not listening, chose CLIENT.
        """
        assert (255 >= ttl >= 1 or ttl is None), "TTL of {} is invalid".format(ttl)
        assert (65536 >= recv_size >= 8), "Receive size of {} is invalid".format(recv_size)
        self.__socket_type = socket_type
        self.implemented_protocol = implemented_protocol
        self.logging = getLogger(logger_name)
        self.group = group
        self.port = port
        self.sock_ttl = ttl or 1
        self.recv_size = recv_size
        self.transport = None
        self._build_socket()
        SocketSelector.add_handler(self)

    def _build_socket(self):
        """Builds the socket accordly to its type

        Note:
            You're still free to call another methods if needed
        """
        if self.__socket_type == DatagramSocket.UNICAST:
            self.build_protocol()
        elif self.__socket_type == DatagramSocket.MULTICAST:
            self.build_protocol()
            self.join_group()
            self.listen()
        else:
            raise ProtocolError("Unkown protocol type")

    def build_protocol(self):
        """Builds UDP protocol supporting the bases of multicast

        Note:
            If you set a TTL larger than 4 and cannot listen/forward
            packages to another subnet, check your LAN settings.
        """
        # Avoid error on class re-use for new connections or dead connections
        if isinstance(self.transport, socket.socket):
            raise MulticastException("A protocol is already defined, you need to destroy it first")
        self.transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                       socket.IPPROTO_UDP)
        self.transport.settimeout(1)
        # NOTE: Set the TTL according to the protocol you're implementing
        # Check RFC/Protocol documentation before setting a HUGE TTL,
        # Some routers/switch may decrease the hops.
        self.transport.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                                  self.sock_ttl)
        try:
            self.transport.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except AttributeError:
            self.logging.warning('Re-use address is not supported')

    def join_group(self):
        """Joins the target multicast group

        Note:
            We're using INADDR_ANY
        """
        if not isinstance(self.transport, socket.socket):
            raise MulticastException("Build a protocol before call join group method")
        try:
            host = struct.pack('4sl', socket.inet_aton(self.group), socket.INADDR_ANY)
            self.transport.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, socket.INADDR_ANY)
            self.transport.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, host)
        except (socket.error, AttributeError, TypeError, NetworkConfigurationError) as error:
            error_msg = 'Could not join multicast group {}:{} \n{}' \
                .format(self.group, self.port, error)
            self.logging.error(error_msg)
            # Force file descriptor closure
            self.destroy()
            raise JoinGroupError(error_msg)

    def send_multicast(self, msg):
        """Multicast a message over the group.

        Args:
            :param msg - String containing udp message to be sent.

        Raises:
            MulticastException - Socket level errors for multicasting

        """
        if not isinstance(self.transport, socket.socket):
            raise MulticastException("Cant send, not connected")

        self.logging.debug('Sending data for target {}:{}:\n{}'
                           .format(self.group, self.port, msg))
        try:
            self.transport.sendto(msg, (self.group, self.port))
        except (socket.error, AttributeError) as mcast_error:
            error_msg = 'Error while sending multicast, reason:{}' \
                .format(mcast_error)
            self.logging.error(error_msg)
            # Force file descriptor closure
            self.destroy()
            raise MulticastException(error_msg)

    def send_unicast(self, msg, *address):
        """Unicast sender
        Args:
            :param msg: message to be sent
            :param address: ip and port target
        Raises:
            UnicastException - Socket level errors for multicasting
        """
        if not isinstance(self.transport, socket.socket):
            raise UnicastException("Cant send, not connected")
        try:
            self.transport.sendto(msg, address)
            self.logging.debug('Send to {}:{} data: \n{}'.format(address[0], address[1], msg))
        except (socket.error, AttributeError) as mcast_error:
            error_msg = 'Error while sending unicast, reason:{}' \
                .format(mcast_error)
            self.logging.error(error_msg)
            # Force file descriptor closure
            self.destroy()
            raise UnicastException(error_msg)

    def listen(self):
        """Bind socket to start listen the multicast group

        Raises:
            MulticastException - Protocol not created
        """
        if not isinstance(self.transport, socket.socket):
            raise MulticastException("A protocol is not defined, cannot bind")
        # Using INADDR_ANY
        self.transport.bind(('0.0.0.0', self.port))

    def recv_dgram(self):
        """Receives a datagram, if any available.

        Returns:
            UdpPackage: A class-like object built on top of namedtuple (read-only)
            Attributes:
                data - Returned data from package (empty if time-out)
                host - sender host
                port - sender port
        """
        data = host = port = ''

        if not isinstance(self.transport, socket.socket):
            raise MulticastException("Cannot recv, not connected")

        try:
            data, (host, port) = self.transport.recvfrom(self.recv_size)
        except socket.timeout as mcast_time_out:
            data = '{}'.format(mcast_time_out)
        except (socket.error, AttributeError) as mcast_error:
            # We won't close the socket file descriptor
            # as we're working with time-out UDP multicast sockets
            error_msg = 'Error receiving socket data: {}' \
                .format(mcast_error)
            self.logging.error(error_msg)
            # Force file descriptor closure
            self.destroy()
            raise UnicastException(error_msg)
        return UdpPackage(data, host, port)

    def destroy(self):
        """Performs graceful shut-down on socket.

        shuts-down both read/write on the file descriptor.
        """
        self.logging.debug('Closing RDWR for socket')
        try:
            self.transport.shutdown(socket.SHUT_RDWR)
        except (socket.error, AttributeError):
            pass
        self.transport = None


def get_host_address(network_interface=None):
    """Gets your active IP Address"""
    try:
        if network_interface not in netifaces.interfaces():
            network_interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        address = netifaces.ifaddresses(network_interface)[netifaces.AF_INET][0]['addr']
    except (ValueError, KeyError):
        raise NetworkConfigurationError("There's a problem on your network configuration, operation cannot proceed")
    return address
