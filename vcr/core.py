# -*- coding: utf-8 -*-
"""
VCR - decorator for capturing and simulating network communication

Any Python socket communication in unittests (decorated with the @vcr function)
and/or doctests (containing a # doctest: +VCR) will be recorded on the first
run and saved into a special 'vcrtapes' directory as single pickled file for
each test case. Future test runs will reuse those recorded network session
allowing for faster tests without any network connection. In order to create
a new recording one just needs to remove/rename the pickled session file(s).

Inspired by:
 * https://docs.python.org/3.6/howto/sockets.html
 * https://github.com/gabrielfalcao/HTTPretty
 * http://code.activestate.com/recipes/408859/

:copyright:
    Robert Barsch (barsch@egu.eu)
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (https://www.gnu.org/copyleft/lesser.html)
"""
from __future__ import absolute_import, division, print_function

import copy
import gzip
import io
import os
import pickle
import select
import socket
import ssl
import sys
import telnetlib
import tempfile
import time
import warnings

from .utils import classproperty, PY2, get_source_code_sha256


VCR_RECORD = 0
VCR_PLAYBACK = 1


orig_socket = socket.socket
orig_sslsocket = ssl.SSLSocket
orig_select_select = select.select
orig_getaddrinfo = socket.getaddrinfo
orig_read_until = telnetlib.Telnet.read_until
if hasattr(select, 'epoll'):
    orig_select_epoll = select.epoll


class VCRException(Exception):
    pass


class VCRRecordingError(VCRException):
    pass


class VCRPlaybackError(VCRException):
    pass


class VCRPlaybackOutgoingTrafficMismatch(VCRPlaybackError):
    """
    Exception that gets raised if the intercepted outgoing traffic on playback
    is not matching the outgoing traffic during recording the VCR tape.
    """
    pass


class VCRPlaybackSourceCodeChangedError(VCRPlaybackError):
    """
    Exception that gets raised if the executed source code has changed since
    recording the VCR tape and at the time of playback.
    """
    pass


class VCRSystem(object):
    """
    Use this class to overwrite default settings on global scale

    >>> from vcr import VCRSystem
    >>> VCRSystem.debug = True
    >>> run_my_tests()
    >>> VCRSystem.reset()

    ``debug`` : bool
        Enables debug mode.
    ``overwrite`` : bool
        Will run vcr in recording mode - overwrites any existing vcrtapes.
    ``playback_only`` : bool
        Will run vcr in playback mode - will not create missing vcrtapes.
    ``disabled`` : bool
        Completely disables vcr - same effect as removing the decorator.
    ``recv_timeout`` : int
        Timeout in seconds used to break socket recv calls (default is 3).
    ``recv_endmarkers`` : list of bytes
        List of end markers which is used to check if a socket recv call
        is finished, e.g. [b'\r\n', b'END\r\n']. Will be ignored if its an
        empty list (default).
    ``recv_size`` : int
        Will request given number of bytes in socket recv calls. Option is
        ignored if not set (default).
    ``raise_if_not_needed`` : bool
        Raise an exception if vcr decorator is not needed because no socket
        traffic has been recorded, instead of just showing a warning.
    ``raise_if_source_code_changed`` : bool
        Raise an exception if the to be executed source code has changed since
        recoring the VCR tape.
    ``raise_outgoing_mismatch`` : bool
        Raise an exception if outgoing traffic encountered during playback is
        not matching pre-recorded traffic in VCR tape.
    ``outgoing_check_normalizations`` : list
        List of functions that normalize outgoing traffic (both actually
        encountered and pre-recorded) before checking for equality of
        encountered and pre-recorded. Each function in the list will be applied
        to outgoing traffic and should have a call syntax of
        ``def custom_normalization(name, args, kwargs)`` and return a list of
        potentially modified ``name, args, kwargs``.
    """
    debug = False
    disabled = False
    overwrite = False
    playback_only = False
    raise_if_not_needed = False
    raise_if_source_code_changed = True
    raise_outgoing_mismatch = True
    outgoing_check_normalizations = []
    recv_timeout = 5
    recv_endmarkers = []
    recv_size = None

    def __init__(self, debug=False):
        self._debug = debug

    def __enter__(self):
        # enable VCR
        if self._debug:
            self._system_debug = VCRSystem.debug
            VCRSystem.debug = True
        VCRSystem.start()

    def __exit__(self, exc_type, exc_value, traceback):  # @UnusedVariable
        # disable VCR
        if self._debug:
            VCRSystem.debug = self._system_debug
        VCRSystem.stop()

    @classmethod
    def reset(cls):
        """
        Reset to default settings
        """
        cls.debug = False
        cls.disabled = False
        cls.overwrite = False
        cls.playback_only = False
        cls.recv_timeout = 5
        cls.recv_endmarkers = []
        cls.recv_size = None
        cls.outgoing_check_normalizations = []

    @classmethod
    def clear_playlist(cls):
        cls.playlist = []

    @classmethod
    def start(cls):
        # reset
        cls.clear_playlist()
        cls.status = VCR_RECORD
        # apply monkey patches
        socket.socket = VCRSocket
        ssl.SSLSocket = VCRSSLSocket
        socket.getaddrinfo = vcr_getaddrinfo
        if hasattr(select, 'epoll'):
            select.epoll = vcr_select_epoll
        if sys.platform == 'win32':
            select.select = vcr_select_select
            telnetlib.Telnet.read_until = vcr_read_until

    @classmethod
    def stop(cls):
        # revert monkey patches
        socket.socket = orig_socket
        ssl.SSLSocket = orig_sslsocket
        socket.getaddrinfo = orig_getaddrinfo
        if hasattr(select, 'epoll'):
            select.epoll = orig_select_epoll
        if sys.platform == 'win32':
            select.select = orig_select_select
            telnetlib.Telnet.read_until = orig_read_until
        # reset
        cls.clear_playlist()
        cls.status = VCR_RECORD

    @classproperty
    def is_recording(cls):  # @NoSelf
        return cls.status == VCR_RECORD

    @classproperty
    def is_playing(cls):  # @NoSelf
        return cls.status == VCR_PLAYBACK

    @classmethod
    def replay_next(cls, name_got, args_got, kwargs_got):
        name_expected, args_expected, kwargs_expected, value_ = \
            cls.playlist.pop(0)
        # XXX: py < 3.5 has sometimes two sendall calls ???
        if sys.version_info < (3, 5):
            if name_got == 'makefile' and name_expected == 'sendall':
                name_expected, args_expected, kwargs_expected, value_ = \
                    cls.playlist.pop(0)
        if cls.debug:
            print('  ', name_got, args_got, kwargs_got, ' | ',
                  name_expected, args_expected, kwargs_expected, '->', value_)
        if cls.raise_outgoing_mismatch:
            # XXX TODO put this into a constant up top!?
            if name_got not in ('recv', 'makefile'):
                # XXX it seems that on Python 2 some 'sendall's for HTTP POST
                # are distributed over two calls, concatenate them here for the
                # check..
                # lookahead to next playlist item
                if (name_got == 'sendall' and args_got and
                        len(args_got) == 1 and
                        args_got[0].startswith(b'POST ') and
                        args_expected[0].endswith(b'\r\n\r\n') and
                        not args_got[0].endswith(b'\r\n\r\n') and
                        cls.playlist):
                    _next_name, _next_args, _next_kwargs, _ = cls.playlist[0]
                    if (_next_name == 'sendall' and len(_next_args) == 1 and
                            _next_kwargs == kwargs_got):
                        args_expected = tuple(
                            [args_expected[0] + _next_args[0]])
                        cls.playlist.pop(0)
                if cls.debug:
                    print('  checking: ', name_got, args_got, kwargs_got,
                          ' | ', name_expected, args_expected, kwargs_expected)
                # apply all normalization functions
                for norm_func in cls.outgoing_check_normalizations:
                    name_got, args_got, kwargs_got = norm_func(
                        name_got, args_got, kwargs_got)
                    name_expected, args_expected, kwargs_expected = norm_func(
                        name_expected, args_expected, kwargs_expected)
                if cls.debug:
                    print('  checking, after normalization: ', name_got,
                          args_got, kwargs_got, ' | ', name_expected,
                          args_expected, kwargs_expected)
                if (name_expected, args_expected, kwargs_expected) != \
                        (name_got, args_got, kwargs_got):
                    msg = '\nExpected: {} {} {}\nGot:      {} {} {}'.format(
                        name_expected, args_expected, kwargs_expected,
                        name_got, args_got, kwargs_got)
                    cls.clear_playlist()
                    raise VCRPlaybackOutgoingTrafficMismatch(msg)
        return value_


def vcr_getaddrinfo(*args, **kwargs):
    if VCRSystem.status == VCR_RECORD:
        # record mode
        value = orig_getaddrinfo(*args, **kwargs)
        VCRSystem.playlist.append(
            ('getaddrinfo', args, kwargs, copy.copy(value)))
        if VCRSystem.debug:
            print('  ', 'vcr_getaddrinfo', args, kwargs, value)
        return value
    else:
        # playback mode
        return VCRSystem.replay_next('getaddrinfo', args, kwargs)


def vcr_select_epoll():
    if VCRSystem.status == VCR_PLAYBACK:
        class FakeEPoll(object):
            def register(self, *args, **kwargs):  # @UnusedVariable
                return True

            def close(self):
                return True

            def poll(self, *args, **kwargs):  # @UnusedVariable
                return []

        return FakeEPoll()
    else:
        return orig_select_epoll()


def vcr_select_select(r, w, x, timeout=None):
    if VCRSystem.status == VCR_PLAYBACK:
        # ugly: requests needs an empty list for r otherwise it disconnects,
        # while obspy.seedlink disconnects if socket is not within w
        # for now it works until the next test case ;/
        return [], w, x
    else:
        return orig_select_select(r, w, x, timeout)


def vcr_read_until(self, match, timeout=None):
    if VCRSystem.status == VCR_PLAYBACK:
        n = len(match)
        self.process_rawq()
        i = self.cookedq.find(match)
        if i >= 0:
            i = i + n
            buf = self.cookedq[:i]
            self.cookedq = self.cookedq[i:]
            return buf
        while not self.eof:
            i = max(0, len(self.cookedq)-n)
            self.fill_rawq()
            self.process_rawq()
            i = self.cookedq.find(match, i)
            if i >= 0:
                i = i+n
                buf = self.cookedq[:i]
                self.cookedq = self.cookedq[i:]
                return buf
        return self.read_very_lazy()
    else:
        return orig_read_until(self, match, timeout=timeout)


class VCRSocket(object):
    """
    """
    def __init__(self, family=socket.AF_INET,
                 type=socket.SOCK_STREAM,  # @ReservedAssignment
                 proto=0, fileno=None, _sock=None):
        if VCRSystem.debug:
            print('  ', '__init__', family, type, proto, fileno)
        self._recording = VCRSystem.is_recording
        self._orig_socket = orig_socket(family, type, proto, fileno)
        # a working file descriptor is needed for telnetlib.Telnet.read_until
        if not self._recording:
            self.fd = tempfile.TemporaryFile()

    def __del__(self):
        if hasattr(self, 'fd'):
            self.fd.close()
        self._orig_socket.close()

    def _exec(self, name, *args, **kwargs):
        if self._recording:
            # record mode
            value = getattr(self._orig_socket, name)(*args, **kwargs)
            if VCRSystem.debug:
                print('  ', name, args, kwargs, value)
            # handle special objects which are not pickleable
            if isinstance(value, io.BufferedIOBase) and \
               not isinstance(value, io.BytesIO):
                temp = io.BytesIO()
                self._orig_socket.setblocking(0)
                self._orig_socket.settimeout(VCRSystem.recv_timeout)
                begin = time.time()
                # recording is slightly slower than running without vcr
                # decorator as we don't know which concept is used to listen
                # on the socket (size, end marker) - we have to wait for a
                # socket timeout - on default its already quite low - but still
                # it introduces a few extra seconds per recv request
                #
                # Note: sometimes recording fails due to the small timeout
                # usually a retry helps - otherwise set the timeout higher for
                # this test case using the recv_timeout parameter
                while True:
                    # endless loop - breaks by checking against recv_timeout
                    if temp.tell() and \
                       time.time() - begin > VCRSystem.recv_timeout:
                        # got some data -> break after recv_timeout
                        break
                    elif time.time() - begin > VCRSystem.recv_timeout * 2:
                        # no data yet -> break after 2 * recv_timeout
                        break

                    try:
                        if VCRSystem.recv_size:
                            data = value.read(len(VCRSystem.recv_size))
                        else:
                            peeked_bytes = value.peek()
                            data = value.read(len(peeked_bytes))
                        if data:
                            temp.write(data)
                            begin = time.time()
                        else:
                            time.sleep(0.1 * VCRSystem.recv_timeout)
                        # speed up closing socket by checking for end markers
                        # by a given recv length
                        if VCRSystem.recv_size:
                            break
                        elif VCRSystem.recv_endmarkers:
                            for marker in VCRSystem.recv_endmarkers:
                                if data.endswith(marker):
                                    break
                    except socket.error:
                        break
                temp.seek(0)
                VCRSystem.playlist.append((name, args, kwargs, temp))
                # return new copy of BytesIO as it may get closed
                return copy.copy(temp)
            # add to playlist
            VCRSystem.playlist.append((name, args, kwargs, copy.copy(value)))
            return value
        else:
            # playback mode
            # get next element in playlist
            return VCRSystem.replay_next(name, args, kwargs)

    def __nonzero__(self):
        return bool(self.__dict__.get('_orig_socket', True))

    def send(self, *args, **kwargs):
        return self._exec('send', *args, **kwargs)

    def sendall(self, *args, **kwargs):
        return self._exec('sendall', *args, **kwargs)

    def fileno(self, *args, **kwargs):
        if self._recording:
            value = self._orig_socket.fileno(*args, **kwargs)
        else:
            value = self.fd.fileno()
        if VCRSystem.debug:
            print('  ', 'fileno', args, kwargs, '->', value)
        return value

    def makefile(self, *args, **kwargs):
        return self._exec('makefile', *args, **kwargs)

    def getsockopt(self, *args, **kwargs):
        return self._exec('getsockopt', *args, **kwargs)

    def setsockopt(self, *args, **kwargs):
        if VCRSystem.debug:
            print('  ', 'setsockopt', args, kwargs)
        if self._recording:
            return self._orig_socket.setsockopt(*args, **kwargs)

    def recv(self, *args, **kwargs):
        return self._exec('recv', *args, **kwargs)

    def close(self):
        if VCRSystem.debug:
            print('  ', 'close')
        return self._orig_socket.close()

    def gettimeout(self, *args, **kwargs):
        return self._exec('gettimeout', *args, **kwargs)

    def settimeout(self, *args, **kwargs):
        if VCRSystem.debug:
            print('  ', 'settimeout', args, kwargs)
        if self._recording:
            return self._orig_socket.settimeout(*args, **kwargs)

    def setblocking(self, *args, **kwargs):
        if VCRSystem.debug:
            print('  ', 'setblocking', args, kwargs)
        if self._recording:
            return self._orig_socket.setblocking(*args, **kwargs)

    def connect(self, *args, **kwargs):
        return self._exec('connect', *args, **kwargs)

    def detach(self, *args, **kwargs):
        return self._exec('detach', *args, **kwargs)

    @property
    def family(self):
        return self._orig_socket.family

    @property
    def type(self):
        return self._orig_socket.type

    @property
    def proto(self):
        return self._orig_socket.proto


class VCRSSLSocket(VCRSocket):
    def __init__(self, sock=None, *args, **kwargs):
        if VCRSystem.debug:
            print('  ', '__init__', args, kwargs)
        self._recording = VCRSystem.is_recording
        self._orig_socket = orig_sslsocket(sock=sock._orig_socket,
                                           *args, **kwargs)
        # a working file descriptor is needed for telnetlib.Telnet.read_until
        if not self._recording:
            self.fd = tempfile.TemporaryFile()

    def getpeercert(self, *args, **kwargs):
        return self._exec('getpeercert', *args, **kwargs)


def vcr(decorated_func=None, debug=False, overwrite=False, disabled=False,
        playback_only=False, tape_name=None):
    """
    Decorator for capturing and simulating network communication

    ``debug`` : bool, optional
        Enables debug mode.
    ``overwrite`` : bool, optional
        Will run vcr in recording mode - overwrites any existing vcrtapes.
    ``playback_only`` : bool, optional
        Will run vcr in playback mode - will not create missing vcrtapes.
    ``disabled`` : bool, optional
        Completely disables vcr - same effect as removing the decorator.
    ``tape_name`` : str, optional
        Use given custom file name instead of an auto-generated name for the
        tape file.
    """
    def _vcr_outer(func):
        """
        Wrapper around _vcr_inner allowing optional arguments on decorator
        """
        def _vcr_inner(*args, **kwargs):
            """
            The actual decorator doing a lot of monkey patching and auto magic
            """
            if disabled or VCRSystem.disabled:
                # execute decorated function without VCR
                return func(*args, **kwargs)

            # prepare VCR tape
            if func.__module__ == 'doctest':
                source_filename = func.__self__._dt_test.filename
                file_name = os.path.splitext(
                    os.path.basename(source_filename))[0]
                # check if a tests directory exists
                path = os.path.join(os.path.dirname(source_filename),
                                    'tests')
                if os.path.exists(path):
                    # ./test/vcrtapes/tape_name.vcr
                    path = os.path.join(os.path.dirname(source_filename),
                                        'tests', 'vcrtapes')
                else:
                    # ./vcrtapes/tape_name.vcr
                    path = os.path.join(os.path.dirname(source_filename),
                                        'vcrtapes')
                func_name = func.__self__._dt_test.name.split('.')[-1]
            else:
                source_filename = func.__code__.co_filename
                file_name = os.path.splitext(
                    os.path.basename(source_filename))[0]
                path = os.path.join(
                    os.path.dirname(source_filename), 'vcrtapes')
                func_name = func.__name__

            if tape_name:
                # tape file name is given - either full path is given or use
                # 'vcrtapes' directory
                if os.sep in tape_name:
                    temp = os.path.abspath(tape_name)
                    path = os.path.dirname(temp)
                    if not os.path.isdir(path):
                        os.makedirs(path)
                tape = os.path.join(path, '%s' % (tape_name))
            else:
                # make sure 'vcrtapes' directory exists
                if not os.path.isdir(path):
                    os.makedirs(path)
                # auto-generated file name
                tape = os.path.join(path, '%s.%s.vcr' % (file_name, func_name))

            # enable VCR
            with VCRSystem(debug=debug):
                # check for tape file and determine mode
                if not (playback_only or VCRSystem.playback_only) and (
                        not os.path.isfile(tape) or
                        overwrite or VCRSystem.overwrite):
                    # record mode
                    if PY2:
                        msg = 'VCR records only in PY3 to be backward ' + \
                              'compatible with PY2 - skipping VCR ' + \
                              'mechanics for %s'
                        warnings.warn(msg % (func.__name__))
                        # disable VCR
                        VCRSystem.stop()
                        # execute decorated function without VCR
                        return func(*args, **kwargs)
                    if VCRSystem.debug:
                        print('\nVCR RECORDING (%s) ...' % (func_name))
                    VCRSystem.status = VCR_RECORD
                    # execute decorated function
                    value = func(*args, **kwargs)
                    # check if vcr is actually used at all
                    if len(VCRSystem.playlist) == 0:
                        msg = 'no socket activity - @vcr unneeded for %s'
                        msg = msg % (func.__name__)
                        if VCRSystem.raise_if_not_needed:
                            raise Exception(msg)
                        else:
                            warnings.warn(msg)
                    else:
                        # add source code hash as first item in playlist
                        sha256 = get_source_code_sha256(func)
                        VCRSystem.playlist.insert(0, sha256)
                        # remove existing tape
                        try:
                            os.remove(tape)
                        except OSError:
                            pass
                        # write playlist to file
                        with gzip.open(tape, 'wb') as fh:
                            pickle.dump(VCRSystem.playlist, fh, protocol=2)
                else:
                    # playback mode
                    if VCRSystem.debug:
                        print('\nVCR PLAYBACK (%s) ...' % (func_name))
                    VCRSystem.status = VCR_PLAYBACK
                    # if playback is requested and tape is missing: raise!
                    if not os.path.exists(tape):
                        msg = 'Missing VCR tape file for playback: {}'
                        raise IOError(msg.format(tape))
                    # load playlist
                    with gzip.open(tape, 'rb') as fh:
                        VCRSystem.playlist = pickle.load(fh)
                    if VCRSystem.debug:
                        print('Loaded playlist:')
                        print('SHA256: {}'.format(VCRSystem.playlist[0]))
                        for i, item in enumerate(VCRSystem.playlist[1:]):
                            print('{:3d}: {} {} {}'.format(i, *item))
                        print()
                    # check if source code has changed
                    sha256_playlist = VCRSystem.playlist.pop(0)
                    if VCRSystem.raise_if_source_code_changed:
                        sha256 = get_source_code_sha256(func)
                        if sha256 != sha256_playlist:
                            msg = ('Source code of test routine has changed '
                                   'since time when VCR tape was recorded '
                                   '(file: {}).').format(tape)
                            raise VCRPlaybackSourceCodeChangedError(msg)
                        if VCRSystem.debug:
                            print('SHA256 sum of source code matches playlist')
                    # execute decorated function
                    value = func(*args, **kwargs)

            return value

        return _vcr_inner

    if decorated_func is None:
        # without arguments
        return _vcr_outer
    else:
        # with arguments
        return _vcr_outer(decorated_func)
