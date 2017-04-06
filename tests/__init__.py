# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import doctest
import unittest


def load_tests(loader, tests, pattern):  # @UnusedVariable
    suite = loader.discover('.')
    # explicit add test_doctest.py doctest as it is not auto-discovered
    suite.addTest(doctest.DocTestSuite('test_doctest'))
    return suite


if __name__ == '__main__':
    unittest.main()
