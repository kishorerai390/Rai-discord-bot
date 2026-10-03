"""
Unit tests for SingleInstanceLock to verify duplicate process prevention.
"""

import unittest
from pathlib import Path
from utils.instance_lock import SingleInstanceLock, InstanceAlreadyRunningError


class TestSingleInstanceLock(unittest.TestCase):
    def setUp(self):
        self.test_lock_file = Path("tests/.test_bot.lock")
        if self.test_lock_file.exists():
            self.test_lock_file.unlink()

    def tearDown(self):
        if self.test_lock_file.exists():
            self.test_lock_file.unlink()

    def test_single_instance_acquisition_and_release(self):
        # Use an alternate port for testing so it doesn't conflict with any active service
        lock1 = SingleInstanceLock(port=49888, lock_file=self.test_lock_file)
        self.assertTrue(lock1.acquire())
        self.assertTrue(self.test_lock_file.exists())
        
        # Second instance should fail while lock1 is held
        lock2 = SingleInstanceLock(port=49888, lock_file=self.test_lock_file)
        with self.assertRaises(InstanceAlreadyRunningError):
            lock2.acquire()

        # Release lock1
        lock1.release()
        self.assertFalse(self.test_lock_file.exists())

        # Now lock2 should be able to acquire
        self.assertTrue(lock2.acquire())
        lock2.release()

    def test_context_manager(self):
        with SingleInstanceLock(port=49889, lock_file=self.test_lock_file):
            self.assertTrue(self.test_lock_file.exists())
            with self.assertRaises(InstanceAlreadyRunningError):
                with SingleInstanceLock(port=49889, lock_file=self.test_lock_file):
                    pass
        self.assertFalse(self.test_lock_file.exists())


if __name__ == "__main__":
    unittest.main()
