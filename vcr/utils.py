# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

from contextlib import contextmanager
import hashlib
import inspect
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
        source_code = ''.join(inspect.getsourcelines(func)[0])
    source_code = source_code.encode('UTF-8')
    return hashlib.sha256(source_code).hexdigest()
