# Domoticz Scripts for WT53R Rain Tank Sensor

This directory contains Domoticz dzVents automation scripts for use with the WT53R Rain Tank Sensor plugin.

## Scripts

### `script_device_deszczowka_automatyka.lua`

**Rainwater Tank Automation** - Automatically manages switching between rainwater and tap water based on tank fill level.

#### Features

✅ **Automatic Switching**
- Switches to tap water when tank level ≤ 20%
- Switches to rainwater when tank level ≥ 40%
- Configurable thresholds and intervals

✅ **Safety Features**
- Minimum 10-minute interval between automatic switches (prevents rapid switching)
- Warning notification when manually switching to rainwater with low level
- Debouncing to prevent multiple triggers from device changes

✅ **Auto-Correction**
- Automatically detects and fixes device mismatches (e.g., after Domoticz restart)
- Works even when auto mode is disabled
- Ensures master switch, valve, and pump are always synchronized

✅ **Manual Override**
- Manual control via master switch
- Auto mode can be enabled/disabled
- All changes are logged with clear markers

#### Required Devices

You must create these devices in Domoticz:

| Device Name | Type | Description |
|-------------|------|-------------|
| `Woda szara` | Selector Switch | Master switch with levels: "Deszczówka", "Woda wodociągowa" |
| `zawór woda szara` | Selector Switch | Valve switch with levels: "deszczówka", "wodociąg" |
| `pompa woda deszczowa` | Switch | Rainwater pump (On/Off) |
| `RainTank - Fill Level` | Percentage | Tank fill level from WT53R plugin (%) |
| `Auto Mode Woda Szara` | Switch | Enable/disable automation |

#### Installation

1. **Copy the script to Domoticz:**
   ```bash
   # Copy to your Domoticz scripts directory
   cp script_device_deszczowka_automatyka.lua /path/to/domoticz/scripts/dzVents/scripts/
   ```

2. **Restart Domoticz** or reload dzVents scripts

3. **Check the log** to verify the script is loaded:
   ```
   dzVents: RAINWATER: ▶ Trigger: ...
   ```

4. **Enable Auto Mode** by turning on the "Auto Mode Woda Szara" switch

#### Configuration

Edit these constants at the top of the `execute` function:

```lua
local MIN_LEVEL = 20              -- Switch to tap water below this %
local MAX_LEVEL = 40              -- Switch to rainwater above this %
local MIN_SWITCH_INTERVAL = 600   -- Minimum seconds between switches (10 min)
local DEBOUNCE_TIME = 5           -- Debounce time in seconds
```

#### How It Works

**Automatic Mode (Auto Mode = On)**

```
Fill Level ≤ 20% → Switches to Tap Water
Fill Level ≥ 40% → Switches to Rainwater
```

**Manual Mode (Auto Mode = Off)**
- You can manually control the master switch
- Devices will still auto-synchronize
- No automatic level-based switching

**Device Synchronization**
- Master Switch = "Deszczówka" → Valve = "deszczówka", Pump = On
- Master Switch = "Woda wodociągowa" → Valve = "wodociąg", Pump = Off

**Mismatch Detection**
- If devices are out of sync (e.g., after restart), they are automatically corrected
- Logged as warnings: `⚠ DEVICE MISMATCH DETECTED!`

#### Example Log Output

```
2025-11-26 23:14:53  dzVents: RAINWATER: ▶ Trigger: Timer (periodic check)
2025-11-26 23:14:53  dzVents: RAINWATER: State: Master=Deszczówka, Valve=deszczówka, Pump=On, Fill=100%
2025-11-26 23:14:53  dzVents: RAINWATER: ✓ No action needed (level 100%, thresholds: 20%-40%)
```

**Auto Switch Example:**
```
2025-11-26 15:30:12  dzVents: RAINWATER: ═══ AUTO SWITCH: Rainwater → Tap Water (level 18% ≤ 20%) ═══
2025-11-26 15:30:12  dzVents: RAINWATER: → Master switch: Tap water
2025-11-26 15:30:12  dzVents: RAINWATER: → Valve: Tap water
2025-11-26 15:30:12  dzVents: RAINWATER: → Pump: Off
```

**Mismatch Correction Example:**
```
2025-11-26 23:14:53  dzVents: RAINWATER: ⚠ DEVICE MISMATCH DETECTED!
2025-11-26 23:14:53  dzVents: RAINWATER:   Expected: Master=Deszczówka → Valve=deszczówka, Pump=On
2025-11-26 23:14:53  dzVents: RAINWATER:   Actual: Valve=wodociąg, Pump=Off
2025-11-26 23:14:53  dzVents: RAINWATER: 🔧 Correcting device mismatch...
2025-11-26 23:14:53  dzVents: RAINWATER: → Valve: Rainwater
2025-11-26 23:14:53  dzVents: RAINWATER: → Pump: On
```

#### Key Features

**Automatic Switching Logic:**
- Switches to tap water when tank level ≤ 20%
- Switches to rainwater when tank level ≥ 40%
- Minimum 10-minute interval between automatic switches

**Device Synchronization:**
- Automatically detects and fixes device mismatches
- Ensures master switch, valve, and pump are always in sync
- Works even when auto mode is disabled (e.g., after Domoticz restart)

**Smart Controls:**
- 5-second debouncing prevents rapid triggers from device changes
- Silent device updates (`.silent()`) to prevent notification spam
- Manual override support with auto mode toggle
- Warning notifications when switching to rainwater with low level

**Robust Logging:**
- Clear, structured logging with emoji markers
- Different log levels (INFO, WARNING, DEBUG)
- Detailed state tracking for troubleshooting

#### Troubleshooting

**Problem: Devices keep getting out of sync**
- Check device names match exactly (case-sensitive)
- Verify selector switch levels are correct
- Check logs for errors

**Problem: Auto mode not working**
- Verify "Auto Mode Woda Szara" switch is On
- Check fill level is outside the 20-40% range
- Ensure minimum switch interval (10 min) has passed

**Problem: Script not running**
- Check dzVents is enabled in Domoticz settings
- Verify script is in correct directory
- Check Domoticz logs for dzVents errors

#### License

This script is part of the WT53R Rain Tank Sensor plugin project.
See main LICENSE file for details.
