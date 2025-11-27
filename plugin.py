#!/usr/bin/env python3
"""
<plugin key="WT53RSensor" name="WT53R Rain Tank Sensor" Author="Wojtek Sawasciuk <voyo@no-ip.pl>"  version="1.0.0">
    <description>
        <h2>WT53R Rain Tank Sensor Plugin</h2>
        <p>This plugin connects to a WT53R range sensor over Modbus TCP protocol 
        to measure water levels in rain tanks. It implements a thread-safe 
        locking mechanism for Modbus communications.</p>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Measures distance from sensor to water surface</li>
            <li>Calculates average readings with outlier rejection</li>
            <li>Determines tank fill percentage and water volume</li>
            <li>Handles maximum water level due to overflow outlets</li>
            <li>Uses thread-safe Modbus communication</li>
            <li>Creates automation devices for dzVents scripts (optional)</li>
        </ul>
        <h3>Devices Created</h3>
        <p><b>Sensor Devices (always created):</b></p>
        <ul style="list-style-type:square">
            <li>Distance - Raw distance measurement</li>
            <li>Distance Avg. - Averaged distance with outlier rejection</li>
            <li>Fill Level - Tank fill percentage</li>
            <li>Volume - Water volume in liters/m³</li>
            <li>Water Level - Water level from bottom in cm</li>
        </ul>
        <p>Note: Full device names in Domoticz will be "HardwareName - DeviceName"</p>
        <p><b>Automation Devices (created but disabled by default):</b></p>
        <ul style="list-style-type:square">
            <li>Woda szara - Master selector switch (for dzVents script)</li>
            <li>zawór woda szara - Valve selector switch (for dzVents script)</li>
            <li>pompa woda deszczowa - Pump On/Off switch (for dzVents script)</li>
            <li>Auto Mode Woda Szara - Enable/disable automation (for dzVents script)</li>
        </ul>
        <p>See <code>domoticz_scripts/README.md</code> for automation script installation.</p>
        <h3>Configuration</h3>
        <ul style="list-style-type:square">
            <li>Address - IP address of RS485-to-TCP adapter</li>
            <li>Port - TCP port for Modbus communication (usually 8887 or 502)</li>
            <li>Mode1 - Modbus Unit ID (hex, e.g., 0x50)</li>
            <li>Mode2 - Poll interval in seconds (default: 180)</li>
            <li>Mode3 - Measurement mode: 1=Short, 2=Medium, 3=Long</li>
            <li>Mode4 - Not used (Reserved for future use)</li>
            <li>Mode5 - JSON with additional configuration like:
                <pre>{
  "tank_height": 135,
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
  "debug_logging": false
}</pre>
            </li>
        </ul>
    </description>
    <params>
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="50px" required="true" default="8887"/>
        <param field="Mode1" label="Unit ID (hex)" width="75px" required="true" default="0x50"/>
        <param field="Mode2" label="Poll Interval (seconds)" width="75px" required="true" default="180"/>
        <param field="Mode3" label="Measurement Mode" width="200px">
            <options>
                <option label="Short (up to 150cm)" value="1" default="false"/>
                <option label="Medium (up to 300cm)" value="2" default="true"/>
                <option label="Long (up to 4m)" value="3" default="false"/>
            </options>
        </param>
        <param field="Mode4" label="Not Used" width="75px" required="false" default=""/>
        <param field="Mode5" label="Advanced Configuration (JSON)" width="350px" required="false" default=""/>
    </params>
</plugin>
"""
import Domoticz
import sys
import os
import time
import json
from datetime import datetime

# Add the plugin directory to the path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import helper modules
from modbus_lock import ModbusLock
from sensor_utils import SensorData

# Ensure pyModbusTCP is available
try:
    from pyModbusTCP.client import ModbusClient
    from pymodbus.constants import Endian
    from pymodbus.payload import BinaryPayloadDecoder
    from pymodbus.payload import BinaryPayloadBuilder
    MODBUS_AVAILABLE = True
except ImportError:
    MODBUS_AVAILABLE = False
    Domoticz.Error(
        "pyModbusTCP is required. Install it using 'pip3 install pyModbusTCP pymodbus'"
    )


# Plugin parameters
class BasePlugin:
    # Plugin constants
    HEARTBEAT_INTERVAL = 10  # seconds between heartbeats
    DEFAULT_POLL_INTERVAL = 180  # seconds between sensor readings (3 minutes)
    SENSOR_MODE_REGISTER = 0x36
    DISTANCE_REGISTER = 0x34

    # Device Units - Sensor Devices
    UNIT_DISTANCE = 1       # Raw distance measurement
    UNIT_DISTANCE_AVG = 2   # Averaged distance measurement (outliers removed)
    UNIT_FILL_PCT = 3       # Tank fill percentage
    UNIT_VOLUME = 4         # Tank water volume (in liters/m³)
    UNIT_WATER_LEVEL = 5    # Water level from bottom of tank (in cm)

    # Device Units - Automation Devices (for dzVents script)
    UNIT_AUTO_MASTER = 6    # Master switch (Deszczówka/Woda wodociągowa)
    UNIT_AUTO_VALVE = 7     # Valve selector (deszczówka/wodociąg)
    UNIT_AUTO_PUMP = 8      # Rainwater pump (On/Off)
    UNIT_AUTO_MODE = 9      # Auto mode enable/disable

    # Sensor Modes
    MODE_SHORT = 1  # Short range (up to 150cm)
    MODE_MEDIUM = 2  # Medium range (up to 300cm)
    MODE_LONG = 3  # Long range (up to 4m)

    def __init__(self):
        """Initialize the plugin"""
        self.enabled = False
        self.heartbeat_count = 0
        self.modbus_client = None
        self.modbus_lock = None
        self.sensor_data = None
        self.last_poll_time = 0
        self.error_count = 0
        self.max_errors = 5
        self.connection_retries = 0

        # Plugin configuration
        self.poll_interval = self.DEFAULT_POLL_INTERVAL
        self.ip_address = ""
        self.port = 0
        self.unit_id = 0
        self.measurement_mode = self.MODE_MEDIUM
        self.tank_height = 135  # Default height in cm
        self.tank_length = 330  # Default length in cm
        self.tank_width = 220  # Default width in cm
        self.pillar_length = 39  # Default pillar length in cm
        self.pillar_width = 24  # Default pillar width in cm
        self.sensor_offset = 186  # Distance from sensor to bottom of empty tank in cm
        self.max_water_level = 111  # Maximum water level from bottom in cm (due to overflow outlet)
        self.min_pump_level = 8  # Minimum water level from bottom in cm (pump can't draw below this level)
        self.averaging_window = 15  # Number of readings to average (covers ~45 minutes of data at 3-minute intervals)
        self.outlier_threshold = 2.0  # Outlier threshold in standard deviations
        self.lock_file_path = None  # Will be set based on config
        self.lock_timeout = 5  # Lock timeout in seconds
        self.debug_logging = False  # Enable debug logging

    def onStart(self):
        """Called when the plugin starts"""
        Domoticz.Log("WT53R Rain Tank Sensor Plugin starting...")

        # Check if pyModbusTCP is available
        if not MODBUS_AVAILABLE:
            Domoticz.Error(
                "Required module pyModbusTCP is missing. Plugin cannot start.")
            return

        # Load configuration
        self.load_configuration()

        # Set debug mode based on configuration
        if self.debug_logging:
            Domoticz.Debugging(1)
            DumpConfigToLog()

        # Create devices if they don't exist
        self.create_devices()

        # Initialize sensor data handler
        self.sensor_data = SensorData(window_size=self.averaging_window,
                                      outlier_threshold=self.outlier_threshold,
                                      logger=Domoticz)

        # Initialize Modbus lock
        self.modbus_lock = ModbusLock(lock_path=self.lock_file_path,
                                      timeout=self.lock_timeout,
                                      logger=Domoticz)

        # Set plugin as enabled
        self.enabled = True
        Domoticz.Log(
            f"WT53R Rain Tank Sensor Plugin started. Polling interval: {self.poll_interval} seconds"
        )

    def onStop(self):
        """Called when the plugin stops"""
        Domoticz.Log("WT53R Rain Tank Sensor Plugin stopping...")
        # Clean up any resources and connections
        if self.modbus_client:
            del self.modbus_client
            self.modbus_client = None
        self.enabled = False
        Domoticz.Log("WT53R Rain Tank Sensor Plugin stopped.")

    def onHeartbeat(self):
        """Called on each heartbeat"""
        # Only proceed if enabled
        if not self.enabled:
            return

        # Increment the heartbeat counter
        self.heartbeat_count += 1

        # Check if it's time to poll the sensor based on poll_interval
        if time.time() - self.last_poll_time >= self.poll_interval:
            Domoticz.Debug("Heartbeat: Time to poll sensor")
            self.poll_sensor()
            self.last_poll_time = time.time()

    def onCommand(self, Unit, Command, Level, Hue):
        """Called when a user command is received from Domoticz"""
        Domoticz.Log(f"onCommand called for Unit {Unit}: Command='{Command}', Level={Level}")

        # Handle automation device commands
        if Unit == self.UNIT_AUTO_MASTER:
            # Master selector switch: Level 0 = Woda wodociągowa, Level 10 = Deszczówka
            Domoticz.Log(f"Master switch command: Level={Level}")
            nValue = 2 if Level > 0 else 0  # Selector nValue: 0=Off, 2=On
            UpdateDevice(Unit, nValue, str(Level), AlwaysUpdate=True)

        elif Unit == self.UNIT_AUTO_VALVE:
            # Valve selector switch: Level 0 = wodociąg, Level 10 = deszczówka
            Domoticz.Log(f"Valve selector command: Level={Level}")
            nValue = 2 if Level > 0 else 0  # Selector nValue: 0=Off, 2=On
            UpdateDevice(Unit, nValue, str(Level), AlwaysUpdate=True)

        elif Unit == self.UNIT_AUTO_PUMP:
            # Pump switch
            if Command == "On":
                Domoticz.Log("Pump turned On")
                UpdateDevice(Unit, 1, "On", AlwaysUpdate=True)
            else:
                Domoticz.Log("Pump turned Off")
                UpdateDevice(Unit, 0, "Off", AlwaysUpdate=True)

        elif Unit == self.UNIT_AUTO_MODE:
            # Auto mode switch
            if Command == "On":
                Domoticz.Log("Auto mode enabled")
                UpdateDevice(Unit, 1, "On", AlwaysUpdate=True)
            else:
                Domoticz.Log("Auto mode disabled")
                UpdateDevice(Unit, 0, "Off", AlwaysUpdate=True)
        else:
            Domoticz.Log(f"Unknown device command for Unit {Unit}", Domoticz.LOG_WARNING)

    def load_configuration(self):
        """Load plugin configuration from Parameters"""
        # Fetch parameters with defaults if not found
        self.ip_address = Parameters[
            "Address"] if "Address" in Parameters else "127.0.0.1"
        self.port = int(Parameters["Port"]) if "Port" in Parameters else 8887
        
        # Handle hex format for unit_id properly
        if "Mode1" in Parameters:
            unit_id_str = Parameters["Mode1"]
            # Check if it's in hex format
            if unit_id_str.lower().startswith("0x"):
                self.unit_id = int(unit_id_str, 16)  # Parse with base 16
            else:
                self.unit_id = int(unit_id_str)  # Parse as decimal
        else:
            self.unit_id = 0x50  # Default value
        self.poll_interval = int(
            Parameters["Mode2"]
        ) if "Mode2" in Parameters else self.DEFAULT_POLL_INTERVAL
        self.measurement_mode = int(
            Parameters["Mode3"]) if "Mode3" in Parameters else self.MODE_MEDIUM

        # Parse JSON configuration for additional parameters
        if "Mode5" in Parameters and Parameters["Mode5"]:
            try:
                config_json = json.loads(Parameters["Mode5"])
                self.tank_height = float(config_json.get("tank_height", 135))
                self.tank_length = float(config_json.get("tank_length", 330))
                self.tank_width = float(config_json.get("tank_width", 220))
                self.pillar_length = float(config_json.get("pillar_length", 39))
                self.pillar_width = float(config_json.get("pillar_width", 24))
                # Get the offset parameter (distance from sensor to bottom of empty tank)
                self.sensor_offset = float(config_json.get("offset", 186))  # Default to 186 cm as per specifications
                # Get the maximum water level (due to overflow outlet)
                self.max_water_level = float(config_json.get("max_water_level", 111))  # Default to 111 cm as per specifications
                # Get the minimum pump level (pump can't draw water below this level)
                self.min_pump_level = float(config_json.get("min_pump_level", 8))  # Default to 8 cm as per specifications
                self.averaging_window = int(
                    config_json.get("averaging_window", 15))
                self.outlier_threshold = float(
                    config_json.get("outlier_threshold", 2.0))
                self.lock_file_path = config_json.get("lock_file_path", None)
                self.lock_timeout = int(config_json.get("lock_timeout", 5))
                self.debug_logging = bool(
                    config_json.get("debug_logging", False))
                self.max_errors = int(config_json.get("max_errors", 5))
            except json.JSONDecodeError as e:
                Domoticz.Error(f"Error parsing JSON configuration: {e}")

        # Log loaded configuration
        Domoticz.Log(
            f"Configuration loaded: IP={self.ip_address}, Port={self.port}, Unit ID=0x{self.unit_id:02X}"
        )
        Domoticz.Log(
            f"Tank config: Height={self.tank_height}cm, Length={self.tank_length}cm, Width={self.tank_width}cm"
        )
        Domoticz.Log(
            f"Pillar dimensions: Length={self.pillar_length}cm, Width={self.pillar_width}cm"
        )
        Domoticz.Log(
            f"Sensor offset: {self.sensor_offset}cm, Max water level: {self.max_water_level}cm, Min pump level: {self.min_pump_level}cm, Averaging window: {self.averaging_window} samples"
        )

    def create_devices(self):
        """Create required Domoticz devices if they don't exist"""
        # Distance sensor (raw readings)
        if self.UNIT_DISTANCE not in Devices:
            Domoticz.Device(
                Name="Distance",
                Unit=self.UNIT_DISTANCE,
                TypeName="Distance",  # Using TypeName for better compatibility
                Used=1).Create()

        # Average distance sensor
        if self.UNIT_DISTANCE_AVG not in Devices:
            Domoticz.Device(
                Name="Distance Avg.",
                Unit=self.UNIT_DISTANCE_AVG,
                TypeName="Distance",  # Using TypeName for better compatibility
                Used=1).Create()

        # Fill percentage
        if self.UNIT_FILL_PCT not in Devices:
            Domoticz.Device(
                Name="Fill Level",
                Unit=self.UNIT_FILL_PCT,
                TypeName="Percentage",  # Using TypeName for better compatibility
                Used=1).Create()

        # Volume - changed to Type=113, Subtype=0 as requested
        if self.UNIT_VOLUME not in Devices:
            Domoticz.Device(
                Name="Volume",
                Unit=self.UNIT_VOLUME,
                Type=113,  # Water (General) device
                Subtype=0,  # Custom sensor
                Switchtype=2,  # Counter
                Used=1,
                Description="Tank water volume in m³").Create()

            Domoticz.Log(f"Created Volume device")

        # Water level (from bottom) - actual water height
        if self.UNIT_WATER_LEVEL not in Devices:
            Domoticz.Device(
                Name="Water Level",
                Unit=self.UNIT_WATER_LEVEL,
                TypeName="Distance",
                Used=1,
                Description="Water level from bottom of tank in cm").Create()

            Domoticz.Log(f"Created Water Level device")

        # === AUTOMATION DEVICES ===
        # These devices are used by the dzVents automation script
        # (domoticz_scripts/script_device_deszczowka_automatyka.lua)

        # Master switch - Main control selector
        if self.UNIT_AUTO_MASTER not in Devices:
            Domoticz.Device(
                Name="Woda szara",
                Unit=self.UNIT_AUTO_MASTER,
                Type=244,  # Switch
                Subtype=62,  # Selector Switch
                Switchtype=18,  # Selector
                Options={
                    "LevelActions": "|",
                    "LevelNames": "Woda wodociągowa|Deszczówka",
                    "LevelOffHidden": "true",
                    "SelectorStyle": "0"
                },
                Used=0,  # Not used by default
                Description="Master switch for rainwater automation (for dzVents script)").Create()

            Domoticz.Log("Created automation device: Woda szara (Master Switch)")

        # Valve selector
        if self.UNIT_AUTO_VALVE not in Devices:
            Domoticz.Device(
                Name="zawór woda szara",
                Unit=self.UNIT_AUTO_VALVE,
                Type=244,  # Switch
                Subtype=62,  # Selector Switch
                Switchtype=18,  # Selector
                Options={
                    "LevelActions": "|",
                    "LevelNames": "wodociąg|deszczówka",
                    "LevelOffHidden": "true",
                    "SelectorStyle": "0"
                },
                Used=0,  # Not used by default
                Description="Valve selector for rainwater automation (for dzVents script)").Create()

            Domoticz.Log("Created automation device: zawór woda szara (Valve Selector)")

        # Pump switch
        if self.UNIT_AUTO_PUMP not in Devices:
            Domoticz.Device(
                Name="pompa woda deszczowa",
                Unit=self.UNIT_AUTO_PUMP,
                Type=244,  # Switch
                Subtype=73,  # Switch
                Switchtype=0,  # On/Off
                Used=0,  # Not used by default
                Description="Rainwater pump switch (for dzVents script)").Create()

            Domoticz.Log("Created automation device: pompa woda deszczowa (Pump Switch)")

        # Auto mode switch
        if self.UNIT_AUTO_MODE not in Devices:
            Domoticz.Device(
                Name="Auto Mode Woda Szara",
                Unit=self.UNIT_AUTO_MODE,
                Type=244,  # Switch
                Subtype=73,  # Switch
                Switchtype=0,  # On/Off
                Used=0,  # Not used by default
                Description="Enable/disable automatic switching (for dzVents script)").Create()

            Domoticz.Log("Created automation device: Auto Mode Woda Szara (Auto Mode Switch)")

    def poll_sensor(self):
        """Poll the WT53R sensor for data"""
        Domoticz.Debug("Polling WT53R sensor...")

        # Check error count to prevent excessive retries
        if self.error_count >= self.max_errors:
            Domoticz.Error(
                f"Too many consecutive errors ({self.error_count}). Skipping poll."
            )
            # Reset error count after time to prevent permanent lockout
            if self.heartbeat_count % 30 == 0:  # Reset after ~30 heartbeats
                self.error_count = 0
            return

        # Attempt to acquire the Modbus lock
        with self.modbus_lock as lock_acquired:
            if not lock_acquired:
                Domoticz.Error("Failed to acquire Modbus lock. Skipping poll.")
                self.error_count += 1
                return

            # Connect to the sensor and get data
            try:
                # Initialize Modbus client if needed
                if not self.modbus_client:
                    self.modbus_client = ModbusClient(host=self.ip_address,
                                                      port=self.port,
                                                      unit_id=self.unit_id,
                                                      auto_open=True,
                                                      auto_close=True,
                                                      timeout=2)

                # Set measurement mode if needed (does not persist in sensor after power loss)
                # We'll try once to set the measurement mode and ignore failure
                success = self.modbus_client.write_single_register(
                    self.SENSOR_MODE_REGISTER, self.measurement_mode)
                if success:
                    Domoticz.Debug(f"Measurement mode set to {self.measurement_mode}")
                else:
                    Domoticz.Debug(f"Failed to set measurement mode, continuing anyway")

                # Read distance value - we'll make only one attempt now for simplicity
                registers = self.modbus_client.read_holding_registers(
                    self.DISTANCE_REGISTER, 1)
                
                if registers is None or len(registers) == 0:
                    Domoticz.Error("Failed to read distance from sensor")
                    self.error_count += 1
                    return

                # Process the raw distance value
                raw_distance = registers[0]
                distance_cm = float(
                    raw_distance) / 10  # Convert to cm if needed

                Domoticz.Debug(
                    f"Raw distance: {raw_distance}, Distance in cm: {distance_cm}"
                )

                # Add to sensor data for averaging
                self.sensor_data.add_data_point(distance_cm)

                # Calculate average distance
                avg_distance = self.sensor_data.get_average()
                if avg_distance is None:
                    avg_distance = distance_cm  # Use raw value if average can't be calculated

                # Use the updated calculate_fill_percentage method with max_water_level parameter
                fill_percentage = self.sensor_data.calculate_fill_percentage(
                    avg_distance, 
                    self.tank_height, 
                    self.sensor_offset,
                    self.max_water_level
                )

                # Calculate volume - parameters for rectangular tank
                tank_params = {
                    'height': self.tank_height,
                    'length': self.tank_length,
                    'width': self.tank_width,
                    'pillar_length': self.pillar_length,
                    'pillar_width': self.pillar_width,
                    'offset': self.sensor_offset,  # Distance from sensor to bottom of empty tank
                    'max_water_level': self.max_water_level,  # Maximum water level due to overflow outlet
                    'min_pump_level': self.min_pump_level  # Minimum water level the pump can draw from
                }

                # Calculate volume - now returns (usable_volume_liters, volume_m3, total_volume_liters)
                volume_result = self.sensor_data.calculate_volume(
                    avg_distance, tank_params)
                
                # Unpack the values - older versions of the function returned only two values
                if len(volume_result) >= 3:
                    usable_volume_liters, volume_m3, total_volume_liters = volume_result
                    Domoticz.Debug(f"Total volume: {total_volume_liters:.1f}L, Usable volume: {usable_volume_liters:.1f}L")
                else:
                    usable_volume_liters, volume_m3 = volume_result
                    total_volume_liters = usable_volume_liters
                    Domoticz.Debug(f"Volume: {usable_volume_liters:.1f}L (legacy calculation)")

                # For very low water levels, use the total volume instead of usable (which might be 0)
                display_volume = usable_volume_liters
                if usable_volume_liters == 0 and total_volume_liters > 0:
                    # If there's water but it's below the min pump level,
                    # show the total volume but indicate it's not usable
                    display_volume = total_volume_liters
                    volume_m3 = total_volume_liters / 1000.0
                    Domoticz.Log(f"Water level below min pump level. Total volume: {total_volume_liters:.1f}L ({volume_m3:.3f}m³) (not pumpable)")

                # Update Domoticz devices
                self.update_devices(distance_cm, avg_distance, fill_percentage,
                                    display_volume)

                # Reset error count on successful read
                self.error_count = 0

            except Exception as e:
                Domoticz.Error(f"Error polling sensor: {e}")
                self.error_count += 1

    def update_devices(self, distance, avg_distance, fill_percentage,
                       volume_liters):
        """Update Domoticz devices with new sensor data"""
        try:
            # Format values for logging
            distance_str = f"{distance:.1f}"
            avg_distance_str = f"{avg_distance:.1f}"
            fill_percentage_str = f"{fill_percentage:.1f}"
            volume_str = f"{volume_liters:.1f}"

            # Calculate m3 for logging
            volume_m3 = volume_liters / 1000.0
            volume_m3_str = f"{volume_m3:.3f}"
            
            # Calculate water level from bottom of tank based on distance measurement and sensor offset
            water_level = max(0, self.sensor_offset - avg_distance)
            water_level_str = f"{water_level:.1f}"
            
            # Log the readings
            Domoticz.Log(
                f"Sensor readings - Distance: {distance_str}cm, Avg: {avg_distance_str}cm, "
                + f"Fill: {fill_percentage_str}%, Volume: {volume_str}L ({volume_m3_str}m³), "
                + f"Water Level: {water_level_str}cm from bottom")

            # Use our UpdateDevice helper function which handles formatting
            # It automatically formats values based on device type and unit
            # AlwaysUpdate=True ensures "Last Seen" timestamp is updated even if value doesn't change
            UpdateDevice(self.UNIT_DISTANCE, 0, distance, AlwaysUpdate=True)
            UpdateDevice(self.UNIT_DISTANCE_AVG, 0, avg_distance, AlwaysUpdate=True)
            UpdateDevice(self.UNIT_FILL_PCT, 0, fill_percentage, AlwaysUpdate=True)

            # Update Volume device with value in liters (Domoticz RFXMeter expects liters)
            UpdateDevice(self.UNIT_VOLUME, 0, volume_liters, AlwaysUpdate=True)

            # Update Water Level device (from bottom of tank)
            UpdateDevice(self.UNIT_WATER_LEVEL, 0, water_level, AlwaysUpdate=True)

        except Exception as e:
            Domoticz.Error(f"Error updating devices: {e}")


global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)


# Generic helper functions
def DumpConfigToLog():
    """Dump plugin configuration to Domoticz log"""
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug(f"Parameter '{x}': '{Parameters[x]}'")
    for x in Devices:
        Domoticz.Debug(f"Device: {Devices[x]}")
        Domoticz.Debug(f"Device ID: {Devices[x].ID}")
        Domoticz.Debug(f"Device Name: {Devices[x].Name}")
        Domoticz.Debug(f"Device nValue: {Devices[x].nValue}")
        Domoticz.Debug(f"Device sValue: {Devices[x].sValue}")
        Domoticz.Debug(f"Device Type: {Devices[x].Type}")
        Domoticz.Debug(f"Device SubType: {Devices[x].SubType}")
        Domoticz.Debug(f"Device Used: {Devices[x].Used}")


def UpdateDevice(Unit, nValue, sValue, TimedOut=0, AlwaysUpdate=False):
    """Update Domoticz device if needed"""
    if Unit in Devices:
        # Get device information for correct formatting
        device_name = Devices[Unit].Name
        device_type = Devices[Unit].Type
        device_subtype = Devices[Unit].SubType
        switchtype = Devices[Unit].SwitchType if hasattr(Devices[Unit], 'SwitchType') else 0
        
        Domoticz.Debug(f"Device {Unit}: {device_name}, Type={device_type}, SubType={device_subtype}, SwitchType={switchtype}")
        
        # Format values based on device type
        formatted_sValue = ""

        # For Volume device (Type=113 RFXMeter expects liters)
        if "Volume" in device_name:
            # Pass the value in liters with 1 decimal place
            volume_liters = float(sValue) if isinstance(sValue, (int, float)) else float(str(sValue))
            formatted_sValue = f"{volume_liters:.1f}"
            Domoticz.Debug(f"Volume in liters: {formatted_sValue}L ({volume_liters/1000:.3f}m³)")
        else:
            # For all other devices, format numeric values with one decimal place
            if isinstance(sValue, (int, float)):
                formatted_sValue = f"{float(sValue):.1f}"
            else:
                formatted_sValue = str(sValue)
        
        # Only update if values changed or always update flag is set
        if Devices[Unit].nValue != nValue or Devices[Unit].sValue != formatted_sValue or \
           Devices[Unit].TimedOut != TimedOut or AlwaysUpdate:
            
            # Log before update
            Domoticz.Debug(f"Before update - Device {Unit}: nValue={Devices[Unit].nValue}, sValue='{Devices[Unit].sValue}'")
            
            try:
                # Just update with positional parameters as per documentation
                # The Multiplier was already set when the device was created
                Devices[Unit].Update(nValue, formatted_sValue)
                
                # Log success
                Domoticz.Log(f"Update {Devices[Unit].Name}: nValue={nValue}, sValue='{formatted_sValue}'")
            except Exception as e:
                Domoticz.Error(f"Update failed: {e} - Device: {Unit}, nValue: {nValue}, sValue: '{formatted_sValue}'")
