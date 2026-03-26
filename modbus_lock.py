#!/usr/bin/env python3
"""
Modbus Locking Module for Domoticz Plugins

This module provides a process-safe locking mechanism for Modbus TCP
communications within Domoticz, using fcntl file locks.
"""
import os
import fcntl
import time
import logging


class ModbusLock:
    """
    Process-safe lock for Modbus communications using fcntl file locking.

    Note: provides inter-process safety only. For intra-process thread safety,
    wrap usage with a threading.Lock in the caller.
    """

    def __init__(self, lock_path=None, timeout=5, logger=None):
        try:
            import Domoticz
            self._domoticz = Domoticz
        except ImportError:
            self._domoticz = None
        self._fallback_logger = logger or logging.getLogger("ModbusLock")

        if lock_path is None:
            if os.access('/var/tmp', os.W_OK):
                self.lock_path = '/var/tmp/domoticz_modbus.lock'
            elif os.access(os.path.expanduser('~'), os.W_OK):
                self.lock_path = os.path.join(os.path.expanduser('~'), '.domoticz_modbus.lock')
            else:
                self.lock_path = './domoticz_modbus.lock'
        else:
            self.lock_path = lock_path

        self.timeout = timeout
        self.lock_file = None
        self._log('log', f"ModbusLock using lock file: {self.lock_path}")

    def _log(self, level, msg):
        """Unified logging for both Domoticz and standalone environments."""
        if self._domoticz is not None:
            {'debug': self._domoticz.Debug,
             'warning': self._domoticz.Warning,
             'error': self._domoticz.Error}.get(level, self._domoticz.Log)(msg)
        else:
            {'debug': self._fallback_logger.debug,
             'warning': self._fallback_logger.warning,
             'error': self._fallback_logger.error}.get(level, self._fallback_logger.info)(msg)

    def acquire(self):
        """
        Acquire the Modbus lock.

        Returns:
            bool: True if lock was acquired successfully, False otherwise.
        """
        start_time = time.time()

        try:
            lock_dir = os.path.dirname(self.lock_path)
            if lock_dir and not os.path.exists(lock_dir):
                try:
                    os.makedirs(lock_dir, exist_ok=True)
                except (IOError, OSError) as e:
                    self._log('error', f"Failed to create lock directory {lock_dir}: {e}")
                    return False

            self.lock_file = open(self.lock_path, 'w+')

            while (time.time() - start_time) < self.timeout:
                try:
                    fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._log('debug', "Successfully acquired Modbus lock")
                    return True
                except IOError:
                    time.sleep(0.1)

            self._log('warning', f"Timeout reached ({self.timeout}s) waiting for Modbus lock")
            return False

        except Exception as e:
            self._log('error', f"Error acquiring Modbus lock: {e}")
            if self.lock_file:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                self.lock_file = None
            return False

    def release(self):
        """Release the Modbus lock."""
        if self.lock_file:
            try:
                fcntl.lockf(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                self._log('debug', "Released Modbus lock")
            except Exception as e:
                self._log('error', f"Error releasing Modbus lock: {e}")
            finally:
                self.lock_file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
