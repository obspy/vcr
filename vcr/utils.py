# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from contextlib import contextmanager
import io
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
