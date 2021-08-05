import time
import unittest
from unittest import mock

from api.timeout import timeout, WorkerException


class TestTimeout(unittest.TestCase):

    def test_timeout(self):
        """
        The process will be killed if it takes too long.
        """

        @timeout(2)
        def func():
            time.sleep(5)
            raise Exception('Was not killed!')

        self.assertRaises(TimeoutError, func)

    def test_timeout_exception(self):
        """
        If the wrapped function has an error, it will raise a WorkerException.
        """

        @timeout(10)
        def func():
            raise ValueError('Cause a worker error!')

        self.assertRaises(WorkerException, func)

    def test_test_timeout(self):
        """Tests can overwrite the timeout"""

        @timeout(0.1)
        def func():
            time.sleep(1)
            return True

        # Killed after 0.1 seconds
        self.assertRaises(TimeoutError, func)

        with mock.patch('api.timeout.TEST_TIMEOUT', 2):
            # New timeout allows the function to finish.
            result = func()
            self.assertTrue(result)
