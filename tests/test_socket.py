# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import select
import socket
import time
import unittest


from vcr import vcr


class SocketTestCase(unittest.TestCase):
    """
    Test suite using socket
    """
    @vcr
    def test_seedlink(self):
        s = socket.socket()
        s.connect(('geofon.gfz-potsdam.de', 18000))
        s.send(b'HELLO\r\n')
        data = s.recv(1024)
        self.assertIn(b'SeedLink', data)

        # obspy.seedlink uses this function to check if socket is still open
        def _is_connected_impl(sock, timeout=4):
            """
            Check a socket for write ability using select()
            """
            start_time = time.time()
            ready_to_write = []
            while (sock not in ready_to_write) and \
                  (time.time() - start_time) < timeout:
                _ready_to_read, ready_to_write, _in_error = \
                    select.select([sock], [sock], [], timeout)
            if sock in ready_to_write:
                return True
            return False

        self.assertTrue(_is_connected_impl(s))
        s.close()

    @vcr
    def test_arclink(self):
        s = socket.socket()
        s.connect(('webdc.eu', 18001))
        s.send(b'HELLO\r\n')
        data = s.recv(1024)
        s.close()
        self.assertIn(b'ArcLink', data)


if __name__ == '__main__':
    unittest.main()
