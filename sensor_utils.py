#!/usr/bin/env python3
"""
Sensor Utilities Module for WT53R Range Sensor Plugin

This module provides utility functions for working with the WT53R range sensor data,
including statistical processing to calculate averages and reject outliers.
"""
import statistics
import logging

class SensorData:
    """
    Class to process and manage sensor data from WT53R range sensor.
    
    This class handles data points, calculates averages, rejects outliers,
    and transforms raw distance measurements into tank fill percentages.
    """
    
    def __init__(self, window_size=10, outlier_threshold=2.0, logger=None):
        """
        Initialize SensorData with configuration parameters.
        
        Args:
            window_size (int, optional): Number of samples to keep in the rolling window.
                                        Defaults to 10.
            outlier_threshold (float, optional): Threshold in standard deviations for outlier 
                                                detection. Defaults to 2.0.
            logger (logging.Logger, optional): Logger object to use. If None, a new logger is created.
        """
        self.window_size = window_size
        self.outlier_threshold = outlier_threshold
        self.data_points = []
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
                # Fall back to standard logging
                self._fallback_logger = logging.getLogger("SensorData")
        
    def add_data_point(self, value):
        """
        Add a new distance measurement to the data window.
        
        Args:
            value (float): The distance measurement to add.
        """
        if value is not None:
            # Basic validity check - reject impossible readings
            if value < 0 or value > 1000:  # unlikely to have measurements over 10 meters or negative values
                if self._log_available:
                    import Domoticz
                    Domoticz.Error(f"Rejecting impossible sensor reading: {value} cm")
                else:
                    self._fallback_logger.error(f"Rejecting impossible sensor reading: {value} cm")
                return
                
            # If we have existing data points, perform a preliminary check for extreme outliers
            if self.data_points and len(self.data_points) >= 3:
                mean = statistics.mean(self.data_points)
                # If the new reading is extremely different from the current average (>5x the outlier threshold),
                # reject it immediately as likely erroneous
                if abs(value - mean) > 5 * self.outlier_threshold * statistics.stdev(self.data_points):
                    if self._log_available:
                        import Domoticz
                        Domoticz.Warning(f"Rejecting extreme outlier: {value} cm (mean: {mean:.2f} cm)")
                    else:
                        self._fallback_logger.warning(f"Rejecting extreme outlier: {value} cm (mean: {mean:.2f} cm)")
                    return
                
            self.data_points.append(float(value))
            # Keep only the most recent window_size points
            self.data_points = self.data_points[-self.window_size:]
            
    def get_average(self):
        """
        Calculate the average of the data points, excluding outliers.
        Implements a more robust approach using multiple methods for outlier detection.
        
        Returns:
            float or None: The average value or None if insufficient data.
        """
        # Handle insufficient data points case
        if not self.data_points:
            return None
        elif len(self.data_points) < 3:  # Need at least 3 points for meaningful statistics
            return sum(self.data_points) / len(self.data_points)
            
        try:
            # Calculate basic statistics
            mean = statistics.mean(self.data_points)
            median = statistics.median(self.data_points)
            stdev = statistics.stdev(self.data_points)
            
            # Check if standard deviation is very small (stable readings)
            if stdev < 0.5:  # If readings are very stable (less than 0.5cm variation)
                if self._log_available:
                    import Domoticz
                    Domoticz.Debug(f"Readings very stable, using direct mean: {mean:.2f} cm")
                return mean
                
            # First-pass filter: simple statistical filter using mean and standard deviation
            filtered_data_1 = [x for x in self.data_points 
                              if abs(x - mean) <= self.outlier_threshold * stdev]
            
            # Second-pass filter: median absolute deviation (MAD) - more robust to extreme outliers
            mad = statistics.median([abs(x - median) for x in self.data_points])
            filtered_data_2 = [x for x in self.data_points 
                              if abs(x - median) <= self.outlier_threshold * 1.4826 * mad]
            
            # Combine the two filtering methods - use intersection of both methods for higher confidence
            filtered_data = list(set(filtered_data_1).intersection(set(filtered_data_2)))
            
            # If filtering removed all points, fall back to the median (more robust than mean)
            if not filtered_data:
                if self._log_available:
                    import Domoticz
                    Domoticz.Warning(f"All data points flagged as outliers. Using median: {median:.2f} cm")
                else:
                    self._fallback_logger.warning(f"All data points flagged as outliers. Using median: {median:.2f} cm")
                return median
                
            # Calculate filtered statistics
            filtered_mean = statistics.mean(filtered_data)
            filtered_median = statistics.median(filtered_data)
            
            # If mean and median differ significantly after filtering, prefer the median
            # (indicates possible remaining skew in the data)
            if abs(filtered_mean - filtered_median) > 2.0:
                if self._log_available:
                    import Domoticz
                    Domoticz.Debug(f"Filtered mean ({filtered_mean:.2f}) and median ({filtered_median:.2f}) differ significantly, using median")
                else:
                    self._fallback_logger.debug(f"Filtered mean ({filtered_mean:.2f}) and median ({filtered_median:.2f}) differ significantly, using median")
                return filtered_median
            
            # Log detailed debug information
            if self._log_available:
                import Domoticz
                Domoticz.Debug(f"Stats - Mean: {mean:.2f}, Median: {median:.2f}, StdDev: {stdev:.2f}, MAD: {mad:.2f}")
                Domoticz.Debug(f"Filtered data points: {len(filtered_data)}/{len(self.data_points)}")
                Domoticz.Debug(f"Filtered mean: {filtered_mean:.2f}, Filtered median: {filtered_median:.2f}")
            else:
                self._fallback_logger.debug(f"Stats - Mean: {mean:.2f}, Median: {median:.2f}, StdDev: {stdev:.2f}, MAD: {mad:.2f}")
                self._fallback_logger.debug(f"Filtered data points: {len(filtered_data)}/{len(self.data_points)}")
                self._fallback_logger.debug(f"Filtered mean: {filtered_mean:.2f}, Filtered median: {filtered_median:.2f}")
            
            return filtered_mean
            
        except Exception as e:
            # Log error
            if self._log_available:
                import Domoticz
                Domoticz.Error(f"Error calculating average: {e}")
            else:
                self._fallback_logger.error(f"Error calculating average: {e}")
            # Fallback to median if statistical methods fail (more robust than mean)
            try:
                return statistics.median(self.data_points)
            except:
                return sum(self.data_points) / len(self.data_points)
            
    def calculate_fill_percentage(self, distance, tank_height, offset=186, max_water_level=None):
        """
        Calculate the tank fill percentage based on measured distance.
        
        Args:
            distance (float): The measured distance from sensor to water level.
            tank_height (float): The total height of the tank (not used in current formula).
            offset (float, optional): Total distance from sensor to bottom of empty tank. Defaults to 186cm.
            max_water_level (float, optional): Maximum water level due to overflow outlet. 
                                              Defaults to None, which means use offset as max level.
        
        Returns:
            float: The calculated fill percentage (0-100).
        """
        try:
            # Calculate water level using the formula: offset - measured_distance
            water_level = offset - distance
            
            # Ensure water level is not negative
            water_level = max(0, water_level)
            
            # If max_water_level is provided, use it as the maximum possible water level
            # Otherwise, use offset as the maximum possible water level
            max_level = max_water_level if max_water_level is not None else offset
            
            # Ensure water level doesn't exceed maximum
            water_level = min(water_level, max_level)
            
            # Calculate fill percentage (water_level / max_level) * 100
            percentage = (water_level / max_level) * 100
            
            # Clamp between 0 and 100
            percentage = max(0, min(100, percentage))
            
            return percentage
            
        except Exception as e:
            # Log error
            if self._log_available:
                import Domoticz
                Domoticz.Error(f"Error calculating fill percentage: {e}")
            else:
                self._fallback_logger.error(f"Error calculating fill percentage: {e}")
            return 0
            
    def calculate_volume(self, distance, tank_params):
        """
        Calculate the volume of water in the tank based on distance measurement.
        
        Args:
            distance (float): The measured distance from sensor to water level.
            tank_params (dict): Dictionary containing tank dimensions and configuration:
                - 'height': Total height of tank
                - 'length': Length of rectangular tank
                - 'width': Width of rectangular tank
                - 'offset': Distance from sensor to bottom of tank when empty
                - 'max_water_level': Maximum possible water level from bottom (defaults to tank height)
                - 'min_pump_level': Minimum water level from bottom that pump can draw (defaults to 0)
        
        Returns:
            tuple: (volume_liters, volume_m3, total_volume_liters) - Volumes in liters and cubic meters
                   volume_liters is the water volume available to the pump (above min_pump_level)
                   total_volume_liters is the total volume including water below min_pump_level
        """
        try:
            # The offset is the total distance from sensor to bottom of tank when empty
            offset = tank_params.get('offset', 186)  # Default to 186 cm
            
            # Calculate water level: offset - measured distance = water height
            water_level = offset - distance
            
            # Ensure water level is not negative
            water_level = max(0, water_level)
            
            # Get maximum water level (default to height if not provided)
            max_water_level = tank_params.get('max_water_level', tank_params.get('height', offset))
            
            # Get minimum water level that pump can draw (default to 8 cm if not provided)
            min_pump_level = tank_params.get('min_pump_level', 8)
            
            # Ensure water level doesn't exceed maximum
            water_level = min(water_level, max_water_level)
            
            # Calculate total volume (all water in the tank)
            length = tank_params.get('length', 0)
            width = tank_params.get('width', 0)
            # Check if we have pillar dimensions to subtract
            pillar_length = tank_params.get('pillar_length', 0)
            pillar_width = tank_params.get('pillar_width', 0)
            
            # Calculate total volume minus pillar volume if dimensions are provided
            if pillar_length > 0 and pillar_width > 0:
                total_volume_cm3 = (length * width * water_level) - (pillar_length * pillar_width * water_level)
            else:
                total_volume_cm3 = length * width * water_level  # Volume in cubic cm
            
            # Convert to liters (dimensions are in cm, so divide by 1000)
            total_volume_liters = total_volume_cm3 / 1000
            
            # Calculate usable water volume (above minimum pump level)
            usable_water_level = max(0, water_level - min_pump_level)
            
            # Calculate usable volume
            if pillar_length > 0 and pillar_width > 0:
                usable_volume_cm3 = (length * width * usable_water_level) - (pillar_length * pillar_width * usable_water_level)
            else:
                usable_volume_cm3 = length * width * usable_water_level  # Volume in cubic cm
            
            # Convert to liters
            usable_volume_liters = usable_volume_cm3 / 1000
            
            # Convert to cubic meters
            volume_m3 = usable_volume_liters / 1000
            
            # Log the calculation details for debugging
            if self._log_available:
                import Domoticz
                Domoticz.Debug(f"Volume calculation: distance={distance:.1f}cm, water_level={water_level:.1f}cm, min_pump={min_pump_level:.1f}cm")
                Domoticz.Debug(f"Total volume: {total_volume_liters:.1f}L, Usable volume: {usable_volume_liters:.1f}L")
            else:
                self._fallback_logger.debug(f"Volume calculation: distance={distance:.1f}cm, water_level={water_level:.1f}cm, min_pump={min_pump_level:.1f}cm")
                self._fallback_logger.debug(f"Total volume: {total_volume_liters:.1f}L, Usable volume: {usable_volume_liters:.1f}L")
            
            return (usable_volume_liters, volume_m3, total_volume_liters)
            
        except Exception as e:
            # Log error
            if self._log_available:
                import Domoticz
                Domoticz.Error(f"Error calculating volume: {e}")
            else:
                self._fallback_logger.error(f"Error calculating volume: {e}")
            return (0, 0, 0)
