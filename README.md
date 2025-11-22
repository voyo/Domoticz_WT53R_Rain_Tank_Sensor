# WT53R Rain Tank Sensor Plugin for Domoticz

This plugin connects to a WT53R range sensor over Modbus TCP protocol to measure water levels in rain tanks. It implements a thread-safe locking mechanism for Modbus communications, ensuring reliable operation in multi-plugin environments.

## Features

- **Advanced Sensor Reading Processing**:
  - 15-sample averaging window (45 minutes of data with 3-minute poll interval)
  - Robust outlier detection with both mean-based and median-based filtering
  - Early rejection of impossible readings (negative values or >10 meters)
  - Optimized 3-minute poll interval to balance data freshness and system load

- **Comprehensive Tank Monitoring**:
  - Accurate water level calculation based on tank dimensions and sensor offset
  - Fill percentage calculation based on maximum water level (accounting for overflow outlets)
  - Volume calculation in liters, accounting for internal tank structures
  - Support for minimum pump level configuration to show actually pumpable water volume

## Installation

1. Stop Domoticz
2. Clone or download this repository to your Domoticz plugins directory
   ```
   cd domoticz/plugins
   git clone https://github.com/voyo/Domoticz_WT53R_Rain_Tank_Sensor.git WT53RSensor
   ```
3. Make sure the Python modules pyModbusTCP and pymodbus are installed:
   ```
   pip3 install pyModbusTCP pymodbus
   ```
4. Start Domoticz
5. Go to "Hardware" page and add new hardware with type "WT53R Rain Tank Sensor"

## Configuration

The plugin supports the following parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| IP Address | IP address of RS485-to-TCP adapter | 127.0.0.1 |
| Port | TCP port for Modbus communication | 8887 |
| Unit ID (hex) | Modbus Unit ID in hex format | 0x50 |
| Poll Interval | Time between sensor readings in seconds | 180 |
| Measurement Mode | Sensor measurement range | Medium (up to 300cm) |
| Tank Height | Height of the tank in centimeters | 200 |
| Advanced Configuration | JSON with additional settings | See below |

### Advanced Configuration (JSON)

The plugin supports an extended set of parameters through a JSON object:

```json
{
  "tank_length": 330,
  "tank_width": 220,
  "pillar_length": 39,
  "pillar_width": 24,
  "offset": 186,
  "max_water_level": 111,
  "min_pump_level": 8,
  "averaging_window": 15,
  "outlier_threshold": 2.0,
  "lock_file_path": "/var/tmp/domoticz_modbus.lock",
  "max_consecutive_errors": 10,
  "debug_logging": false
}
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| tank_length | Length of the tank in cm | 330 |
| tank_width | Width of the tank in cm | 220 |
| pillar_length | Length of internal pillar support in cm | 39 |
| pillar_width | Width of internal pillar support in cm | 24 |
| offset | Distance from sensor to bottom of empty tank in cm | 186 |
| max_water_level | Maximum water level from bottom in cm (due to overflow outlet) | 111 |
| min_pump_level | Minimum water level from bottom in cm (pump can't draw below this) | 8 |
| averaging_window | Number of readings to keep for averaging | 15 |
| outlier_threshold | Threshold in standard deviations for outlier detection | 2.0 |
| lock_file_path | Path to Modbus lock file | None (auto) |
| max_consecutive_errors | Maximum consecutive errors before applying exponential backoff | 10 |
| debug_logging | Enable detailed debug logging | false |

## Created Devices

The plugin creates five devices in Domoticz:

1. **Rain Tank Distance** - Raw distance measurement from sensor to water (cm)
2. **Rain Tank Distance Average** - Averaged distance with outliers removed (cm)
3. **Rain Tank Fill Level** - Tank fill percentage (%)
4. **Rain Tank Volume** - Calculated water volume (m³)
5. **Rain Tank Water Level** - Water height from bottom of tank (cm)

## Technical Details

### Error Handling and Recovery

The plugin implements robust error handling with automatic recovery:

- **Exponential Backoff**: After consecutive errors, the plugin applies exponential backoff (2^n seconds, max 5 minutes) before retrying
- **Automatic Reconnection**: After 3 consecutive errors, the Modbus client is recreated to handle stale connections
- **No Permanent Lockout**: Unlike previous versions, the plugin never stops polling permanently - it will always retry with appropriate delays
- **Detailed Logging**: All errors are logged with both consecutive and total error counts for better diagnostics

This ensures the plugin recovers automatically from temporary network issues, device restarts, or connection timeouts without requiring manual intervention.

### Thread-Safe Modbus Communications

This plugin implements a file-based locking mechanism to ensure thread-safe access to Modbus devices when multiple plugins access the same hardware. This is especially important in Docker environments where multiple containers may be communicating with the same physical devices.

### Averaging Algorithm

The plugin uses a sophisticated statistical approach for calculating averages:

1. Maintains a rolling window of the last N readings (configurable)
2. Performs double-pass outlier detection:
   - Mean ± (threshold × standard deviation)
   - Median ± (threshold × median absolute deviation)
3. Uses the intersection of both filtering methods for higher confidence
4. Falls back to median if filtering removes all points

### Volume Calculation

Volume calculation takes into account:
- Rectangular tank dimensions (length, width)
- Internal pillars or supports that reduce volume
- Maximum water level due to overflow outlets
- Minimum pump water level (water that can't be extracted by pump)

The plugin now calculates two volume values:
1. **Usable Volume** - Water volume above the minimum pump level (can be pumped out)
2. **Total Volume** - All water in the tank, including water below the minimum pump level

For very low water levels (below the minimum pump level), the plugin will:
- Show 0.0L for usable volume in the standard device reading
- Log the total non-pumpable volume in Domoticz logs for reference
- Include both values in diagnostic outputs

## License

This plugin is licensed under the Apache-2.0 License. See the LICENSE file for details.
