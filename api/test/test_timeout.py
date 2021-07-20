import time
import unittest
from unittest import mock

from api.timeout import timeout, WorkerException


class TestTimeout(unittest.TestCase):

    def test_timeout(self):
        @timeout(2)
        def func():
            count = 5
            while count > 0:
                count -= 1
                time.sleep(1)
            raise Exception('Was not killed!')

        self.assertRaises(TimeoutError, func)

    def test_timeout_exception(self):
        @timeout(10)
        def func():
            raise ValueError('Cause a worker error!')

        self.assertRaises(WorkerException, func)

    def test_test_timeout(self):
        """Tests can overwrite the timeout"""

        @timeout(0.1)
        def func():
            time.sleep(1)

        # Killed after 0.1 seconds
        self.assertRaises(TimeoutError, func)

        with mock.patch('api.timeout.TEST_TIMEOUT', 2):
            # New timeout allows the function to finish.
            result = func()
            self.assertIsNone(result)
