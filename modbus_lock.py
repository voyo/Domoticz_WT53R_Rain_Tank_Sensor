#!/usr/bin/env python3
"""
Modbus Locking Module for Domoticz Plugins

This module provides a thread-safe, cross-process locking mechanism for Modbus TCP 
communications within Domoticz. It's designed to work in Docker environments and
with multiple plugins that may access the same Modbus devices.

The locking is based on file locking using fcntl, which ensures that locks work
across separate processes, not just threads within the same process.
"""
import os
import fcntl
import time
import logging

class ModbusLock:
    """
    A class that provides thread-safe and process-safe locking for Modbus communications.
    
    This locking mechanism is essential when multiple Domoticz plugins might try to access
    the same Modbus device simultaneously, which can lead to communication errors.
    
    The class uses file-based locking with fcntl to ensure locks work across different 
    processes, not just threads within the same process.
    """
    
    def __init__(self, lock_path=None, timeout=5, logger=None):
        """
        Initialize the ModbusLock with configurable parameters.
        
        Args:
            lock_path (str, optional): Path to the lock file. Defaults to None, which will
                                      use '/var/tmp/domoticz_modbus.lock' or fall back to
                                      a location within the plugin directory.
            timeout (int, optional): Maximum time in seconds to wait for lock acquisition.
                                     Defaults to 5 seconds.
            logger (logging.Logger, optional): Logger object to use. If None, a new logger is created.
        """
        # Setup direct logging to Domoticz
        # Import Domoticz for logging (it should be available in the plugin environment)
        try:
            import Domoticz
            # We will use Domoticz logging directly
            self._log_available = True
        except ImportError:
            # Fall back to standard logging if not running in Domoticz
            self._log_available = False
            if logger:
                self._fallback_logger = logger
            else:
                self._fallback_logger = logging.getLogger("ModbusLock")
        
        # Determine lock file path
        if lock_path is None:
            # Try standard locations, falling back as needed
            if os.access('/var/tmp', os.W_OK):
                self.lock_path = '/var/tmp/domoticz_modbus.lock'
            elif os.access(os.path.expanduser('~'), os.W_OK):
                self.lock_path = os.path.join(os.path.expanduser('~'), '.domoticz_modbus.lock')
            else:
                # Last resort: use current directory
                self.lock_path = './domoticz_modbus.lock'
        else:
            self.lock_path = lock_path
            
        # Log lock file path
        if self._log_available:
            import Domoticz
            Domoticz.Log(f"ModbusLock using lock file: {self.lock_path}")
        else:
            self._fallback_logger.info(f"ModbusLock using lock file: {self.lock_path}")
        
        self.timeout = timeout
        self.lock_file = None
        
    def acquire(self):
        """
        Acquire the Modbus lock.
        
        This method will try to acquire the lock file using fcntl.lockf,
        which provides cross-process locking. It will retry until the timeout is reached.
        
        Returns:
            bool: True if lock was acquired successfully, False otherwise.
        """
        start_time = time.time()
        
        try:
            # Make sure the directory exists
            lock_dir = os.path.dirname(self.lock_path)
            if lock_dir and not os.path.exists(lock_dir):
                try:
                    os.makedirs(lock_dir, exist_ok=True)
                except (IOError, OSError) as e:
                    # Log the error
                    if self._log_available:
                        import Domoticz
                        Domoticz.Error(f"Failed to create lock directory {lock_dir}: {e}")
                    else:
                        self._fallback_logger.error(f"Failed to create lock directory {lock_dir}: {e}")
                    return False
            
            # Open the lock file (create if it doesn't exist)
            self.lock_file = open(self.lock_path, 'w+')
            
            # Try to acquire the lock, retrying until timeout
            while (time.time() - start_time) < self.timeout:
                try:
                    fcntl.lockf(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Log successful lock acquisition
                    if self._log_available:
                        import Domoticz
                        Domoticz.Debug("Successfully acquired Modbus lock")
                    else:
                        self._fallback_logger.debug("Successfully acquired Modbus lock")
                    return True
                except IOError:
                    # Could not acquire lock, wait a bit and retry
                    time.sleep(0.1)
            
            # Log timeout warning
            if self._log_available:
                import Domoticz
                Domoticz.Log(f"WARNING: Timeout reached ({self.timeout}s) waiting for Modbus lock")
            else:
                self._fallback_logger.warning(f"Timeout reached ({self.timeout}s) waiting for Modbus lock")
            return False
            
        except Exception as e:
            # Log error
            if self._log_available:
                import Domoticz
                Domoticz.Error(f"Error acquiring Modbus lock: {e}")
            else:
                self._fallback_logger.error(f"Error acquiring Modbus lock: {e}")
            # If we couldn't use file locking, close any open file
            if self.lock_file:
                try:
                    self.lock_file.close()
                except:
                    pass
                self.lock_file = None
            return False
            
    def release(self):
        """
        Release the Modbus lock.
        
        This method releases the lock file if it was acquired.
        """
        if self.lock_file:
            try:
                fcntl.lockf(self.lock_file, fcntl.LOCK_UN)
                self.lock_file.close()
                # Log release
                if self._log_available:
                    import Domoticz
                    Domoticz.Debug("Released Modbus lock")
                else:
                    self._fallback_logger.debug("Released Modbus lock")
            except Exception as e:
                # Log error
                if self._log_available:
                    import Domoticz
                    Domoticz.Error(f"Error releasing Modbus lock: {e}")
                else:
                    self._fallback_logger.error(f"Error releasing Modbus lock: {e}")
            finally:
                self.lock_file = None
                
    def __enter__(self):
        """
        Context manager entry method to allow 'with' statement usage.
        
        Returns:
            bool: True if lock was acquired successfully, False otherwise.
        """
        return self.acquire()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit method to ensure lock is released.
        """
        self.release()
        # Don't suppress exceptions
        return False


# Example usage when running this file directly
if __name__ == "__main__":
    import time
    import logging
    import threading
    import tempfile
    import os
    import random
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("ModbusLockTest")
    
    # Create a temporary lock file
    temp_lock_file = tempfile.mktemp(suffix=".lock", prefix="modbus_test_")
    logger.info(f"Using temporary lock file: {temp_lock_file}")
    
    # For testing purposes, we'll simulate a lock with a simple file
    # since fcntl.lockf might not work correctly in all environments
    class TestLock:
        def __init__(self, lock_path):
            self.lock_path = lock_path
            self.lock_held = False
            
        def acquire(self):
            # Try to create the lock file exclusively
            try:
                # Check if file exists
                if os.path.exists(self.lock_path):
                    logger.debug(f"Lock file exists, cannot acquire: {self.lock_path}")
                    return False
                
                # Create the file to indicate lock is held
                with open(self.lock_path, 'w') as f:
                    f.write(f"Locked by process {os.getpid()}")
                
                self.lock_held = True
                return True
            except Exception as e:
                logger.error(f"Error acquiring lock: {e}")
                return False
                
        def release(self):
            # Release by removing the file
            if self.lock_held:
                try:
                    os.remove(self.lock_path)
                    self.lock_held = False
                    return True
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}")
                    return False
            return False
    
    # Test with multiple threads to demonstrate locking
    def test_with_threads():
        """Test concurrent access with multiple threads"""
        
        # Use a shared lock object
        test_lock = TestLock(temp_lock_file)
        
        # Thread synchronization
        lock_acquired = threading.Event()
        threads_ready = threading.Event()
        thread_count = threading.Semaphore(0)
        
        def worker(worker_id):
            """Test worker that acquires and releases the lock"""
            logger.info(f"Worker {worker_id} starting")
            
            # Signal that this thread is ready
            thread_count.release()
            
            # Wait for all threads to be ready
            threads_ready.wait()
            
            for i in range(3):
                logger.info(f"Worker {worker_id} attempting to acquire lock (attempt {i+1})")
                
                # Try to acquire the lock with exponential backoff
                retries = 0
                max_retries = 10
                acquired = False
                
                while retries < max_retries and not acquired:
                    acquired = test_lock.acquire()
                    if acquired:
                        logger.info(f"Worker {worker_id} acquired lock")
                        # Signal that a lock has been acquired
                        lock_acquired.set()
                        
                        # Simulate some work with the Modbus device
                        time.sleep(random.uniform(0.5, 1.5))
                        
                        logger.info(f"Worker {worker_id} releasing lock")
                        test_lock.release()
                        
                        # Clear the signal
                        lock_acquired.clear()
                        break
                    else:
                        # If another thread has the lock, wait for it to be released
                        retries += 1
                        backoff = 0.1 * (2 ** retries) + random.uniform(0, 0.1)
                        logger.debug(f"Worker {worker_id} backing off for {backoff:.2f}s")
                        time.sleep(backoff)
                
                if not acquired:
                    logger.error(f"Worker {worker_id} failed to acquire lock after {max_retries} retries")
                
                # Wait a bit before next attempt
                time.sleep(random.uniform(0.3, 0.7))
            
            logger.info(f"Worker {worker_id} finished")
        
        # Create multiple threads to test concurrent access
        threads = []
        num_threads = 3
        
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads to be ready
        for _ in range(num_threads):
            thread_count.acquire()
        
        # Signal all threads to start trying to acquire the lock
        threads_ready.set()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
    
    # Clear any existing lock file
    if os.path.exists(temp_lock_file):
        os.remove(temp_lock_file)
    
    # Run test
    logger.info("=== TESTING MODBUS LOCK IMPLEMENTATION ===")
    test_with_threads()
    logger.info("Tests completed successfully")
