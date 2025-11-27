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

**Devices created by WT53R plugin (automatic):**

| Device Name | Full Name in Domoticz | Description |
|-------------|----------------------|-------------|
| Fill Level | `RainTank - Fill Level` | Tank fill percentage from WT53R sensor |
| Volume | `RainTank - Volume` | Water volume in liters/m³ |
| Distance | `RainTank - Distance` | Raw distance measurement |
| Distance Avg. | `RainTank - Distance Avg.` | Averaged distance |
| Water Level | `RainTank - Water Level` | Water level from bottom |

**Devices you must create manually (Dummy devices with HTTP actions):**

These devices need to be created as **Dummy** devices to support HTTP URL configuration for controlling physical hardware (GPIO, ESPEasy, etc.):

| Device Name | Full Name | Type | HTTP Actions | Purpose |
|-------------|-----------|------|--------------|---------|
| RainTank - Woda szara | `RainTank - Woda szara` | Selector Switch | No | Master selector for visualization |
| RainTank - zawór woda szara | `RainTank - zawór woda szara` | Selector Switch | **Yes** ✅ | Controls valve via HTTP/GPIO |
| RainTank - pompa woda deszczowa | `RainTank - pompa woda deszczowa` | On/Off Switch | **Yes** ✅ | Controls pump via HTTP/GPIO |
| RainTank - Auto Mode Woda Szara | `RainTank - Auto Mode Woda Szara` | On/Off Switch | No | Enable/disable automation |

**Important:** Device names MUST match exactly (including "RainTank - " prefix) for the dzVents script to work!

#### How to Create Dummy Devices

**Step 1: Add Dummy Hardware** (if not already added)

1. Go to **Setup → Hardware**
2. Add new hardware:
   - Name: `Dummy` (or any name)
   - Type: `Dummy (Does nothing, use for virtual switches only)`
3. Click **Add**

**Step 2: Create Virtual Sensors**

Click **Create Virtual Sensors** button in the Dummy hardware row, then create each device:

**2.1 Master Selector Switch**
- Name: `RainTank - Woda szara`
- Sensor Type: `Switch → Selector`
- Click **OK**
- After creation, click **Edit** on the device:
  - Actions: Leave empty (no HTTP needed)
  - Selector Levels: Edit to have: `Woda wodociągowa` (level 0), `Deszczówka` (level 10)

**2.2 Valve Selector Switch** (with HTTP actions)
- Name: `RainTank - zawór woda szara`
- Sensor Type: `Switch → Selector`
- Click **OK**
- After creation, click **Edit** on the device:
  - **Set Point 0 (wodociąg):**
    - Level: `0`, Name: `wodociąg`
    - On URL: `http://YOUR_ESPEASY_IP/control?cmd=GPIO,12,0` (example - set valve to tap water)
  - **Set Point 10 (deszczówka):**
    - Level: `10`, Name: `deszczówka`
    - On URL: `http://YOUR_ESPEASY_IP/control?cmd=GPIO,12,1` (example - set valve to rainwater)

**2.3 Pump Switch** (with HTTP actions)
- Name: `RainTank - pompa woda deszczowa`
- Sensor Type: `Switch → Switch`
- Click **OK**
- After creation, click **Edit** on the device:
  - On Action: `http://YOUR_ESPEASY_IP/control?cmd=GPIO,13,1` (example - turn pump on)
  - Off Action: `http://YOUR_ESPEASY_IP/control?cmd=GPIO,13,0` (example - turn pump off)

**2.4 Auto Mode Switch**
- Name: `RainTank - Auto Mode Woda Szara`
- Sensor Type: `Switch → Switch`
- Click **OK**
- After creation, click **Edit** on the device:
  - Actions: Leave empty (no HTTP needed)

**Step 3: Verify Device Names**

Go to **Devices** and verify that all device names match exactly:
- `RainTank - Fill Level` (from plugin)
- `RainTank - Woda szara` (Dummy)
- `RainTank - zawór woda szara` (Dummy)
- `RainTank - pompa woda deszczowa` (Dummy)
- `RainTank - Auto Mode Woda Szara` (Dummy)

**Notes:**
- Replace `YOUR_ESPEASY_IP` with your actual ESPEasy device IP
- Replace GPIO numbers (12, 13) with your actual GPIO pins
- You can use any HTTP control system: ESPEasy, Tasmota, Shelly, etc.
- Test HTTP URLs manually first before configuring automation

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
