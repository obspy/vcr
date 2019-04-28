# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import unittest

from vcr import vcr, VCRSystem
from vcr.utils import _normalize_http_header

try:
    # Py3
    from urllib.parse import urlencode
    from http.client import HTTPConnection, HTTPSConnection
except ImportError:
    # Py2
    from urllib import urlencode
    from httplib import HTTPConnection, HTTPSConnection


class HTTPClientTestCase(unittest.TestCase):
    """
    Test suite using requests
    """
    def setUp(self):
        VCRSystem.outgoing_check_normalizations = [
            _normalize_http_header]

    def tearDown(self):
        VCRSystem.reset()

    def test_connectivity(self):
        # basic network connection test to exclude network issues
        conn = HTTPSConnection("www.python.org")
        conn.request("GET", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.reason, 'OK')
        conn.close()

    @vcr
    def test_http_get(self):
        conn = HTTPConnection("www.python.org")
        conn.request("GET", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 301)
        self.assertEqual(response.reason, 'Moved Permanently')

        conn.close()

    @vcr
    def test_http_get_invalid(self):
        conn = HTTPConnection("httpstat.us")
        conn.request("GET", "/404")
        response = conn.getresponse()
        self.assertEqual(response.status, 404)
        self.assertEqual(response.reason, 'Not Found')
        conn.close()

    @vcr
    def test_https_get(self):
        conn = HTTPSConnection("www.python.org")
        conn.request("GET", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.reason, 'OK')
        conn.close()

    @vcr
    def test_https_head(self):
        conn = HTTPSConnection("www.python.org")
        conn.request("HEAD", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.reason, 'OK')
        data = response.read()
        self.assertEqual(len(data), 0)
        self.assertEqual(data, b'')
        conn.close()

    @vcr
    def test_redirect_to_https(self):
        conn = HTTPSConnection("obspy.org")
        conn.request("GET", "/")
        response = conn.getresponse()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.reason, 'Moved Temporarily')
        conn.close()

    @vcr
    def test_http_post(self):
        params = urlencode([('@number', 12524), ('@type', 'issue'),
                            ('@action', 'show')])
        headers = {"Content-type": "application/x-www-form-urlencoded",
                   "Accept": "text/plain"}
        conn = HTTPConnection("bugs.python.org")
        conn.request("POST", "", params, headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 302)
        self.assertEqual(response.reason, 'Found')
        data = response.read()
        self.assertIn(b'Redirecting', data)
        conn.close()


if __name__ == '__main__':
    unittest.main()
