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

    Handles data points, calculates averages with outlier rejection,
    and transforms raw distance measurements into tank fill percentages.
    """

    # Minimum stdev floor in cm — prevents over-rejection when readings are very stable.
    # Without this floor, stdev≈0 causes the preliminary outlier check to reject
    # any new reading that differs even slightly from the current window mean.
    MIN_STDEV_CM = 1.0

    def __init__(self, window_size=10, outlier_threshold=2.0, min_distance=50.0, max_distance=200.0, logger=None):
        self.window_size = window_size
        self.outlier_threshold = outlier_threshold
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.data_points = []
        try:
            import Domoticz
            self._domoticz = Domoticz
        except ImportError:
            self._domoticz = None
        self._fallback_logger = logger or logging.getLogger("SensorData")

    def _log(self, level, msg):
        """Unified logging for both Domoticz and standalone environments."""
        if self._domoticz is not None:
            {'debug': self._domoticz.Debug,
             'warning': self._domoticz.Log,
             'error': self._domoticz.Error}.get(level, self._domoticz.Log)(msg)
        else:
            {'debug': self._fallback_logger.debug,
             'warning': self._fallback_logger.warning,
             'error': self._fallback_logger.error}.get(level, self._fallback_logger.info)(msg)

    def add_data_point(self, value):
        """Add a new distance measurement to the data window. Returns True if accepted."""
        if value is None:
            return False

        if value <= 0 or value > 1000:
            self._log('error', f"Rejecting impossible sensor reading: {value} cm")
            return False

        if value < self.min_distance:
            self._log('warning', f"Rejecting reading below min_distance: {value} cm (min: {self.min_distance} cm)")
            return False

        if value > self.max_distance:
            self._log('warning', f"Rejecting reading above max_distance: {value} cm (max: {self.max_distance} cm)")
            return False

        if self.data_points:
            mean = statistics.mean(self.data_points)
            stdev = statistics.stdev(self.data_points) if len(self.data_points) >= 3 else 0
            effective_stdev = max(stdev, self.MIN_STDEV_CM)
            if abs(value - mean) > 5 * self.outlier_threshold * effective_stdev:
                self._log('warning', f"Rejecting extreme outlier: {value} cm (mean: {mean:.2f} cm, effective_stdev: {effective_stdev:.2f} cm)")
                return False

        self.data_points.append(float(value))
        self.data_points = self.data_points[-self.window_size:]
        return True

    def get_average(self):
        """
        Calculate the average of the data points, excluding outliers.

        Returns:
            float or None: The average value or None if no data points.
        """
        if not self.data_points:
            return None
        if len(self.data_points) < 3:
            return sum(self.data_points) / len(self.data_points)

        try:
            mean = statistics.mean(self.data_points)
            median = statistics.median(self.data_points)
            stdev = statistics.stdev(self.data_points)

            if stdev < 0.5:
                self._log('debug', f"Readings very stable, using direct mean: {mean:.2f} cm")
                return mean

            filtered_data_1 = [x for x in self.data_points
                               if abs(x - mean) <= self.outlier_threshold * stdev]

            mad = statistics.median([abs(x - median) for x in self.data_points])
            filtered_data_2 = [x for x in self.data_points
                               if abs(x - median) <= self.outlier_threshold * 1.4826 * mad]

            filtered_data = list(set(filtered_data_1).intersection(set(filtered_data_2)))

            if not filtered_data:
                self._log('warning', f"All data points flagged as outliers. Using median: {median:.2f} cm")
                return median

            filtered_mean = statistics.mean(filtered_data)
            filtered_median = statistics.median(filtered_data)

            if abs(filtered_mean - filtered_median) > 2.0:
                self._log('debug', f"Filtered mean ({filtered_mean:.2f}) and median ({filtered_median:.2f}) differ significantly, using median")
                return filtered_median

            self._log('debug', f"Stats - Mean: {mean:.2f}, Median: {median:.2f}, StdDev: {stdev:.2f}, MAD: {mad:.2f}")
            self._log('debug', f"Filtered {len(filtered_data)}/{len(self.data_points)} points, mean: {filtered_mean:.2f} cm")

            return filtered_mean

        except Exception as e:
            self._log('error', f"Error calculating average: {e}")
            try:
                return statistics.median(self.data_points)
            except Exception:
                return sum(self.data_points) / len(self.data_points)

    def calculate_fill_percentage(self, distance, tank_height, offset=186, max_water_level=None):
        """
        Calculate the tank fill percentage based on measured distance.

        Args:
            distance: Distance from sensor to water surface (cm).
            tank_height: Total tank height — unused, kept for API compatibility.
            offset: Distance from sensor to bottom of empty tank (cm).
            max_water_level: Maximum water level due to overflow outlet (cm).

        Returns:
            float: Fill percentage (0-100).
        """
        try:
            water_level = max(0, offset - distance)
            max_level = max_water_level if max_water_level is not None else offset
            if max_level <= 0:
                self._log('error', f"Invalid max_level ({max_level}), cannot calculate fill percentage")
                return 0
            water_level = min(water_level, max_level)
            return max(0.0, min(100.0, (water_level / max_level) * 100))
        except Exception as e:
            self._log('error', f"Error calculating fill percentage: {e}")
            return 0

    def calculate_volume(self, distance, tank_params):
        """
        Calculate the volume of water in the tank.

        Args:
            distance: Distance from sensor to water surface (cm).
            tank_params: Dict with tank dimensions:
                offset, length, width, pillar_length, pillar_width,
                max_water_level, min_pump_level.

        Returns:
            tuple: (usable_volume_liters, volume_m3, total_volume_liters)
        """
        try:
            offset = tank_params.get('offset', 186)
            water_level = min(
                max(0, offset - distance),
                tank_params.get('max_water_level', tank_params.get('height', offset))
            )
            min_pump_level = tank_params.get('min_pump_level', 8)

            length = tank_params.get('length', 0)
            width = tank_params.get('width', 0)
            pillar_length = tank_params.get('pillar_length', 0)
            pillar_width = tank_params.get('pillar_width', 0)

            def net_area(h):
                base = length * width * h
                if pillar_length > 0 and pillar_width > 0:
                    base -= pillar_length * pillar_width * h
                return base

            total_volume_liters = net_area(water_level) / 1000
            usable_water_level = max(0, water_level - min_pump_level)
            usable_volume_liters = net_area(usable_water_level) / 1000
            volume_m3 = usable_volume_liters / 1000

            self._log('debug', f"Volume: distance={distance:.1f}cm, water_level={water_level:.1f}cm, "
                               f"total={total_volume_liters:.1f}L, usable={usable_volume_liters:.1f}L")

            return (usable_volume_liters, volume_m3, total_volume_liters)

        except Exception as e:
            self._log('error', f"Error calculating volume: {e}")
            return (0, 0, 0)
