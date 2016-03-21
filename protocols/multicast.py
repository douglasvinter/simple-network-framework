# -*- coding: utf-8 -*-
"""Base UDP Multicast.
Relaying only on pure Python socket API
"""


__author__ = 'douglasvinter'
__version__ = '0.1'


import socket
from logging import getLogger
from collections import namedtuple

# udp_pkg used to return datagram status
# Class-like declaration
UdpPackage = namedtuple('udp_pkg', ('data', 'host', 'port'))


class MulticastException(Exception):
    """ Exception base class for multicast errors

    Args:
        msg (str): Human readable string describing the exception.

    Attributes:
        msg (str): Human readable string describing the exception.
    """

    def __init__(self, msg):
        super(MulticastException, self).__init__(msg)


class JoinGroupError(MulticastException):
    """ Exception subclass for join group operation

    Args:
        msg (str): Human readable string describing the exception.

    Attributes:
        msg (str): Human readable string describing the exception.
    """
    pass


class UnicastResponseError(MulticastException):
    """ Exception subclass for unicast recv operation

    Args:
        msg (str): Human readable string describing the exception.

    Attributes:
        msg (str): Human readable string describing the exception.
    """
    pass


class Multicast(object):
    """A pure python Class for Network Multicast

    This class was based in some extent of Twisted networking mechanism but much simpler.
    It basically provides the bases of multicast enabling you to join into IGMP groups.

    Note:
        If you're thinking on use this class to bind into multiple IGMP groups you've joined,
        feel free to, but check your max_memberships flag first.
        (Linux - /proc/sys/net/ipv4/igmp_max_memberships)
    """

    _group = ''
    _port = 0
    _sock = None
    _sock_ttl = 1
    _sock_timeout = None
    _recv_size = 1024

    @property
    def group(self):
        """str(group) returns network address for listening."""
        return Multicast._group

    @group.setter
    def group(self, mcast_group):
        Multicast._group = mcast_group

    @property
    def port(self):
        """int(port) returns integer port number.

        Note:
            If 0, socket will use it arbitrary
        """
        return Multicast._port

    @port.setter
    def port(self, port):
        Multicast._port = int(port)

    @property
    def recv_size(self):
        """int(recvBufferSize) returns bytes expected to be recv.

        Note:
            Max UDP Package size is 64Kb
        Args:
            :param recvSize - Integer bit size, default is 1024b
        """
        return Multicast._recv_size

    @recv_size.setter
    def recv_size(self, recv_size):
        Multicast._recv_size = recv_size

    @property
    def transport(self):
        """Socket object"""
        return Multicast._sock

    @transport.setter
    def transport(self, udp_proto):
        Multicast._sock = udp_proto

    @property
    def sock_ttl(self):
        """Define the Time To Live of the protocol you're implementing,

        Args:
            sock_ttl - int value from 1 to 255, that means the amount of networks you expect
            to forward your messages.
        """
        return Multicast._sock_ttl

    @sock_ttl.setter
    def sock_ttl(self, sock_ttl):
        if 1 >= sock_ttl <= 255:
            Multicast._sock_ttl = sock_ttl

    @property
    def sock_timeout(self):
        """Returns socket time-out, used to create the socket on build_protocol method.

        Note:
            time-out value of None means that your socket is BLOCKING, you may block
            IO threads depending on how you've done the callBack mechanism.
        """
        return Multicast._sock_timeout

    @sock_timeout.setter
    def sock_timeout(self, sock_timeout):
        Multicast._sock_timeout = sock_timeout

    @property
    def is_connected(self):
        """Helps to check if the connection is alive or not,
        could be done with transport itself."""
        if isinstance(self.transport, socket.socket):
            return True
        else:
            return False

    def __init__(self, logger_name):
        """Multicast constructor

        Args:
            :param logger_name - Valid logger name.
        """
        self.logging = getLogger(logger_name)

    def build_protocol(self):
        """Builds UDP protocol supporting the bases of multicast

        Note:
            If you set a TTL larger than 4 and cannot listen/forward
            packages to another subnet, check your LAN settings.
        """
        # Avoid error on class re-use for new connections or dead connections
        if isinstance(self.transport, socket.socket):
            self.destroy()
        self.transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, \
            socket.IPPROTO_UDP)
        self.transport.settimeout(self.sock_timeout)
        # NOTE: Set the TTL according to the protocol you're implementing
        # Check RFC/Protocol documentation before setting a HUGE TTL,
        # Some routers/switch may decrease the hops.
        self.transport.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, \
            self.sock_ttl)
        try:
            self.transport.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except AttributeError:
            self.logging.warning('Re-use address is not supported')

    def get_host_address(self):
        """Gets your own IP Address
        
        Note:
            This method is a fallback in case your distro /etc/hosts
            is not configured properly or if you have any network problems.
        """
        try:
            return socket.gethostbyname(socket.gethostname())
        except socket.error:
            self.logging.warning('your /etc/hosts does not resolve your address, trying to resolve over DNS query')
        try:
            dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # NOTE depending on your network setup this may look like 
            # a sort of DNS cache poisoning, but its just a simple resolve.
            dns.connect(('8.8.8.8', 53))
            host = dns.getsockname()
            dns.shutdown(socket.SHUT_RDWR)
        except (socket.error, AttributeError):
            pass
        if isinstance(host, (list, tuple)):
            return host[0]
        else:
            raise JoinGroupError('Network is not properly configured on this system')
                
    def join_group(self):
        """Joins multicast group"""
        try:
            host = self.get_host_address()
            self.transport.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, \
                socket.inet_aton(host))
            self.transport.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, \
                socket.inet_aton(self.group) + socket.inet_aton(host))
        except (socket.error, AttributeError, TypeError) as mcast_error:
            error_msg = 'Could not join multicast group {}:{} \n{}' \
                .format(self.group, self.port, mcast_error)
            self.logging.error(error_msg)
            # Force file descriptor closure
            self.destroy()
            raise JoinGroupError(error_msg)

    def mcast_dgram(self, msg):
        """Multicast a message over the group."""
        self.logging.debug('Sending data for target {}:{}:\n{}' \
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
            raise UnicastResponseError(error_msg)
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
