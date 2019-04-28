# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import unittest

from vcr import vcr, VCRSystem
from vcr.utils import _normalize_http_header


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
    def setUp(self):
        VCRSystem.outgoing_check_normalizations = [
            _normalize_http_header]

    def tearDown(self):
        # reset to default settings
        VCRSystem.reset()

    @vcr
    def test_serverproxy(self):
        server = ServerProxy("http://betty.userland.com")
        self.assertEqual(server.examples.getStateName(41), 'South Dakota')


if __name__ == '__main__':
    unittest.main()
