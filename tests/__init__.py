# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import unittest


def load_tests(loader, tests, pattern):  # @UnusedVariable
    return loader.discover('.')


if __name__ == '__main__':
    unittest.main()
