# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import doctest
import unittest

import requests

from vcr import vcr


# monkey patch DocTestCase
def runTest(self):  # NOQA
    if '+VCR' in self._dt_test.docstring:
        return vcr(self._runTest)()
    return self._runTest()


if getattr(doctest.DocTestCase, '_runTest', None) is None:
    doctest.DocTestCase._runTest = doctest.DocTestCase.runTest
    doctest.DocTestCase.runTest = runTest
    doctest.register_optionflag('VCR')


def some_function_with_doctest(url):
    """
    My test function

    Usage:
    >>> some_function_with_doctest('https://www.python.org')  # doctest: +VCR
    200
    """
    r = requests.get(url)
    return r.status_code


def suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
