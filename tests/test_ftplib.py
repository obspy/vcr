# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import ftplib
import io
import unittest

from vcr import vcr
from vcr.utils import catch_stdout


class FTPLibTestCase(unittest.TestCase):
    """
    Test suite using ftplib.
    """
    @vcr(disabled=True)
    def test_ftp(self):
        # connect to host, default port
        with catch_stdout():
            ftp = ftplib.FTP('ftp.debian.org')
        resp = ftp.login()
        self.assertEqual(resp, '230 Login successful.')
        # change into "debian" directory
        resp = ftp.cwd('debian')
        self.assertEqual(resp, '250 Directory successfully changed.')
        # list directory contents
        with catch_stdout() as out:
            resp = ftp.retrlines('LIST')
        self.assertIn('README', out.getvalue())
        self.assertEqual(resp, '226 Directory send OK.')
        # retrieve file
        temp = io.BytesIO()
        resp = ftp.retrbinary('RETR README', temp.write)
        self.assertEqual(resp, '226 Transfer complete.')
        # check content
        temp.seek(0)
        self.assertIn(b'Debian', temp.read())
        temp.close()
        ftp.quit()

    @vcr(disabled=True)
    def test_ftp_tls(self):
        with catch_stdout():
            ftps = ftplib.FTP_TLS('ftp.pureftpd.org')
        resp = ftps.login()
        self.assertEqual(resp, '230 Anonymous user logged in')
        resp = ftps.prot_p()
        self.assertEqual(resp, '200 Data protection level set to "private"')
        ftps.quit()


if __name__ == '__main__':
    unittest.main()
