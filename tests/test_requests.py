# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import json
import tempfile
import unittest

import requests

from vcr import vcr, VCRSystem
from vcr.utils import _normalize_http_header


class RequestsTestCase(unittest.TestCase):
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
        r = requests.get('https://www.python.org/')
        self.assertEqual(r.status_code, 200)

    @vcr
    def test_http_get(self):
        r = requests.get('http://httpbin.org/status/200')
        self.assertEqual(r.status_code, 200)

    @vcr
    def test_http_post(self):
        payload = dict(key1='value1', key2='value2')
        r = requests.post('http://httpbin.org/post', data=payload)
        out = json.loads(r.text)
        self.assertEqual(out['form'], {'key1': 'value1', 'key2': 'value2'})

    @vcr
    def test_http_post_file(self):
        VCRSystem.outgoing_check_normalizations = [
            _normalize_http_header]
        try:
            with tempfile.TemporaryFile(mode='wb+') as file:
                file.write(b'test123')
                file.seek(0)
                files = {'file': file}
                r = requests.post('http://httpbin.org/post', files=files)
            out = json.loads(r.text)
            self.assertEqual(out['files']['file'], 'test123')
        finally:
            VCRSystem.outgoing_check_normalizations = []

    @vcr
    def test_cookies(self):
        cookies = dict(cookies_are='working')
        r = requests.get('http://httpbin.org/cookies', cookies=cookies)
        out = json.loads(r.text)
        self.assertEqual(out['cookies'], {"cookies_are": "working"})

    @vcr
    def test_cookie_jar(self):
        jar = requests.cookies.RequestsCookieJar()
        jar.set('tasty_cookie', 'yum', domain='httpbin.org', path='/cookies')
        jar.set('gross_cookie', 'blech', domain='httpbin.org', path='/null')
        r = requests.get('http://httpbin.org/cookies', cookies=jar)
        out = json.loads(r.text)
        self.assertEqual(out['cookies'], {"tasty_cookie": "yum"})

    @vcr
    def test_https_get(self):
        r = requests.get('https://www.python.org/')
        self.assertEqual(r.status_code, 200)

    @vcr
    def test_allow_redirects_false(self):
        # 1
        r = requests.get('http://github.com/', allow_redirects=False)
        self.assertEqual(r.status_code, 301)  # Moved Permanently
        self.assertEqual(r.url, 'http://github.com/')
        self.assertEqual(r.headers['Location'], 'https://github.com/')
        # 2
        r = requests.get('http://obspy.org/', allow_redirects=False)
        self.assertEqual(r.status_code, 302)  # Found (Moved Temporarily)
        self.assertEqual(r.url, 'http://obspy.org/')
        self.assertEqual(r.headers['Location'],
                         'https://github.com/obspy/obspy/wiki/')

    @vcr
    def test_redirect(self):
        r = requests.get('http://github.com/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.url, 'https://github.com/')
        self.assertEqual(len(r.history), 1)

    @vcr
    def test_sessions(self):
        s = requests.Session()
        s.get('http://httpbin.org/cookies/set/sessioncookie/123456789')
        r = s.get('http://httpbin.org/cookies')
        out = json.loads(r.text)
        self.assertEqual(out['cookies'], {"sessioncookie": "123456789"})

    @vcr
    def test_sessions2(self):
        s = requests.Session()
        s.auth = ('user', 'pass')
        s.headers.update({'x-test': 'true'})
        r = s.get('http://httpbin.org/headers', headers={'x-test2': 'true'})
        out = json.loads(r.text)
        self.assertEqual(out['headers']['X-Test'], 'true')
        self.assertEqual(out['headers']['X-Test2'], 'true')

    @vcr
    def test_redirect_twice(self):
        # http://obspy.org redirects to https://github.com/obspy/obspy/wiki
        r = requests.get('http://obspy.org/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.history), 2)

    @vcr
    def test_get_fdsn(self):
        r = requests.get('http://service.iris.edu/fdsnws/event/1/contributors')
        self.assertEqual(r.status_code, 200)

    @vcr
    def test_get_obspy_example(self):
        ua = 'ObsPy/0.0.0+archive (Windows-10-10.0.14393, Python 2.7.11)'
        headers = {'User-Agent': ua}
        r = requests.get('https://examples.obspy.org/test.sac', stream=True,
                         headers=headers)
        self.assertEqual(r.status_code, 200)


if __name__ == '__main__':
    unittest.main()
