# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from contextlib import contextmanager
import hashlib
import inspect
import io
import re
import sys
import unittest


try:
    from contextlib import redirect_stdout
except ImportError:
    # Python < 3.4
    @contextmanager
    def redirect_stdout(new_target):
        old_target, sys.stdout = sys.stdout, new_target
        try:
            yield new_target
        finally:
            sys.stdout = old_target


try:
    # PY2
    PY2 = True
    from StringIO import StringIO as CaptureIO  # @UnresolvedImport
except ImportError:
    # PY3
    PY2 = False

    class CaptureIO(io.TextIOWrapper):
        def __init__(self):
            super(CaptureIO, self).__init__(io.BytesIO(), encoding='UTF-8',
                                            newline='', write_through=True)

        def getvalue(self):
            return self.buffer.getvalue().decode('UTF-8')


def catch_stdout():
    return redirect_stdout(CaptureIO())


class classproperty(object):
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, _owner_self, owner_cls):
        return self.fget(owner_cls)


def skip_if_py2(func):
    def wrapper(*args, **kwargs):
        if PY2:
            raise unittest.SkipTest('recording in PY2 is not supported')
        return func(*args, **kwargs)
    return wrapper


def get_source_code_sha256(func):
    """
    Lookup source code of unittest test method or doctest and
    calculate SHA256 hash.
    """
    if not inspect.isfunction(func) and not inspect.ismethod(func):
        raise TypeError()
    # doctest
    if func.__module__ == 'doctest':
        source_code = ''.join(example.source for example in
                              func.__self__._dt_test.examples)
    # unittest test method
    else:
        # omit first line, which is the @vcr decorator line
        source_code = ''.join(inspect.getsourcelines(func)[0][1:])
    source_code = source_code.encode('UTF-8')
    return hashlib.sha256(source_code).hexdigest()


def _normalize_http_header(name, args, kwargs):
    """
    normalize http headers in outgoing traffic:

    Expected: sendall (b'POST /post HTTP/1.1\r\n'
        b'Host: httpbin.org\r\n'
        b'User-Agent: python-requests/2.13.0\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: */*\r\n'
        b'Connection: keep-alive\r\n'
        b'Content-Length: 147\r\n'
        b'Content-Type: multipart/form-data; '
        b'boundary=45c2c6ddafe3498c94b4554d6fb6e503\r\n\r\n',) {}
    Got:      sendall (b'POST /post HTTP/1.1\r\n'
        b'Host: httpbin.org\r\n'
        b'User-Agent: python-requests/2.13.0\r\n'
        b'Accept-Encoding: gzip, deflate\r\n'
        b'Accept: */*\r\n'
        b'Connection: keep-alive\r\n'
        b'Content-Length: 147\r\n'
        b'Content-Type: multipart/form-data; '
        b'boundary=9ce384e773e444fc9ae202103e971aab\r\n\r\n',) {}
    """
    if name != 'sendall':
        return name, args, kwargs
    if len(args) != 1:
        return name, args, kwargs
    if b'HTTP' in args[0]:
        # sort HTTP headers
        # example:
        # (b'GET /fdsnws/event/1/contributors HTTP/1.1\r\n'
        #  b'Host: service.iris.edu\r\nAccept-Encoding: gzip, deflate\r\n'
        #  b'User-Agent: python-requests/2.13.0\r\nConnection: keep-alive\r\n'
        #  b'Accept: */*\r\n\r\n')
        x = args[0]
        x = x.split(b'\r\n')
        # two empty items at the end
        x = x[:1] + sorted(x[1:-2]) + x[-2:]
        x = b'\r\n'.join(x)
        args = tuple([x])

        # normalize user-agent string
        pattern = (
            b'User-Agent: python-requests/.*?(\\r\\n)')
        repl = b'User-Agent: python-requests/x.x.x\\1'
        args = tuple([re.sub(pattern, repl, args[0], count=1)])

        # normalize 'boundary=...' string
        pattern = (
            b'(boundary)=[0-9a-fA-F]{32}((\\r\\n)|(;))')
        repl = b'\\1=xxx\\2'
        args = tuple([re.sub(pattern, repl, args[0], count=1)])
    elif args[0].startswith(b'--'):
        # treat follow-up line with above boundary string.. right now our
        # normalization is only aware of the current line.. this should be
        # changed, we should normalize on the whole playlist to be able to
        # properly handle such matches that appear over multiple lines..

        # normalize boundary strings on follow-up lines
        pattern = b'--[0-9a-fA-F]{32}'
        repl = b'--' + b'x' * 32
        args = tuple([re.sub(pattern, repl, args[0])])
    return name, args, kwargs
