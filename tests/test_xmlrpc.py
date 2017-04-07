# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import unittest

from vcr import vcr


try:
    # Py3
    from xmlrpc.client import ServerProxy
except ImportError:
    # Py2
    from xmlrpclib import ServerProxy


class XMLRPCTestCase(unittest.TestCase):
    """
    Test suite using xmlrpc
    """
    @vcr
    def test_serverproxy(self):
        server = ServerProxy("http://betty.userland.com")
        self.assertEqual(server.examples.getStateName(41), 'South Dakota')


if __name__ == '__main__':
    unittest.main()
