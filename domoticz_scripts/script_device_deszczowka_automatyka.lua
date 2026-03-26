--[[
    Rainwater Tank Automation Script for Domoticz

    Automatically switches between rainwater and tap water based on tank fill level:
    - Switches to tap water when level <= 20%
    - Switches to rainwater when level >= 40%
    - Prevents rapid switching with minimum 10-minute interval
    - Auto-corrects device mismatches (e.g., after Domoticz restart)
    - Supports manual override with auto mode toggle

    Devices required:
    - 'Woda szara' - Master selector switch (Deszczówka/Woda wodociągowa)
    - 'zawór woda szara' - Valve selector (deszczówka/wodociąg)
    - 'pompa woda deszczowa' - Rainwater pump (On/Off)
    - 'RainTank - Fill Level' - Tank fill level percentage sensor
    - 'Auto Mode Woda Szara' - Auto mode enable/disable switch
]]

-- Helper functions defined before main return block
local function switchToRainwater(domoticz, masterSwitch, valve, pump)
    local changed = false
    if masterSwitch.levelName ~= 'Deszczówka' then
        masterSwitch.switchSelector('Deszczówka').silent()
        domoticz.log('→ Master switch: Rainwater', domoticz.LOG_INFO)
        changed = true
    end
    if valve.levelName ~= 'deszczówka' then
        valve.switchSelector('deszczówka').silent()
        domoticz.log('→ Valve: Rainwater', domoticz.LOG_INFO)
        changed = true
    end
    if pump.state ~= 'On' then
        pump.switchOn().silent()
        domoticz.log('→ Pump: On', domoticz.LOG_INFO)
        changed = true
    end
    return changed
end

local function switchToTapWater(domoticz, masterSwitch, valve, pump)
    local changed = false
    if masterSwitch.levelName ~= 'Woda wodociągowa' then
        masterSwitch.switchSelector('Woda wodociągowa').silent()
        domoticz.log('→ Master switch: Tap water', domoticz.LOG_INFO)
        changed = true
    end
    if valve.levelName ~= 'wodociąg' then
        valve.switchSelector('wodociąg').silent()
        domoticz.log('→ Valve: Tap water', domoticz.LOG_INFO)
        changed = true
    end
    if pump.state ~= 'Off' then
        pump.switchOff().silent()
        domoticz.log('→ Pump: Off', domoticz.LOG_INFO)
        changed = true
    end
    return changed
end

local function syncDevicesWithMaster(domoticz, masterSwitch, valve, pump)
    if masterSwitch.levelName == 'Deszczówka' then
        return switchToRainwater(domoticz, masterSwitch, valve, pump)
    elseif masterSwitch.levelName == 'Woda wodociągowa' then
        return switchToTapWater(domoticz, masterSwitch, valve, pump)
    end
    return false
end

local function checkDeviceMismatch(masterSwitch, valve, pump)
    if masterSwitch.levelName == 'Deszczówka' then
        return valve.levelName ~= 'deszczówka' or pump.state ~= 'On'
    elseif masterSwitch.levelName == 'Woda wodociągowa' then
        return valve.levelName ~= 'wodociąg' or pump.state ~= 'Off'
    end
    return false
end

-- Main script definition
return {
    on = {
        devices = {
            'RainTank - Woda szara',
            'RainTank - Fill Level',
            'RainTank - Auto Mode Woda Szara'
        },
        timer = {
            'every 10 minutes'
        }
    },

    logging = {
        level = domoticz.LOG_INFO,
        marker = 'RAINWATER'
    },

    data = {
        lastSwitchTime = { initial = 0 },
        lastRunTime = { initial = 0 }
    },

    execute = function(domoticz, item)
        -- === CONFIGURATION ===
        local MIN_LEVEL = 20              -- Switch to tap water below this %
        local MAX_LEVEL = 40              -- Switch to rainwater above this %
        local MIN_SWITCH_INTERVAL = 600   -- Minimum seconds between auto switches (10 min)
        local DEBOUNCE_TIME = 5           -- Seconds to debounce device changes

        -- === DEVICE REFERENCES ===
        local masterSwitch = domoticz.devices('RainTank - Woda szara')
        local valve = domoticz.devices('RainTank - zawór woda szara')
        local pump = domoticz.devices('RainTank - pompa woda deszczowa')
        local fillLevel = domoticz.devices('RainTank - Fill Level')
        local autoMode = domoticz.devices('RainTank - Auto Mode Woda Szara')

        local currentTime = os.time()
        local currentLevel = fillLevel.percentage

        -- === LOG TRIGGER SOURCE ===
        if item.isTimer then
            domoticz.log('▶ Trigger: Timer (periodic check)', domoticz.LOG_INFO)
        elseif item.isDevice then
            domoticz.log('▶ Trigger: Device "' .. item.name .. '" changed', domoticz.LOG_INFO)
        end

        -- === LOG CURRENT STATE ===
        domoticz.log(string.format('State: Master=%s, Valve=%s, Pump=%s, Fill=%d%%',
            masterSwitch.levelName, valve.levelName, pump.state, currentLevel),
            domoticz.LOG_INFO)

        -- === DEBOUNCING (skip rapid triggers from device changes) ===
        if not item.isTimer then
            local timeSinceLastRun = currentTime - domoticz.data.lastRunTime
            if timeSinceLastRun < DEBOUNCE_TIME then
                domoticz.log('⏸ Debouncing: Only ' .. timeSinceLastRun .. 's since last run',
                    domoticz.LOG_DEBUG)
                return
            end
        end
        domoticz.data.lastRunTime = currentTime

        -- === AUTO MODE TOGGLE HANDLING ===
        if item.isDevice and item.name == 'Auto Mode Woda Szara' then
            domoticz.log('Auto mode changed to: ' .. autoMode.state, domoticz.LOG_INFO)
            -- Check for device mismatch and fix it
            if checkDeviceMismatch(masterSwitch, valve, pump) then
                domoticz.log('⚠ Device mismatch detected, correcting...', domoticz.LOG_WARNING)
                syncDevicesWithMaster(domoticz, masterSwitch, valve, pump)
            end
            return
        end

        -- === MANUAL CONTROL ===
        if item.isDevice and item.name == 'Woda szara' then
            domoticz.log('═══ MANUAL SWITCH ═══', domoticz.LOG_INFO)
            domoticz.data.lastSwitchTime = currentTime

            -- Warn if manually switching to rainwater with low level
            if masterSwitch.levelName == 'Deszczówka' and currentLevel < MIN_LEVEL then
                local msg = string.format('Low water in tank (%d%%) for rainwater mode!', currentLevel)
                domoticz.notify('Rainwater Warning', msg, domoticz.PRIORITY_NORMAL)
                domoticz.log('⚠ WARNING: ' .. msg, domoticz.LOG_WARNING)
            end

            -- Sync all devices with master switch
            syncDevicesWithMaster(domoticz, masterSwitch, valve, pump)
            return
        end

        -- === CHECK FOR DEVICE MISMATCH (always fix, regardless of auto mode) ===
        if checkDeviceMismatch(masterSwitch, valve, pump) then
            domoticz.log('⚠ DEVICE MISMATCH DETECTED!', domoticz.LOG_WARNING)
            domoticz.log(string.format('  Expected: Master=%s → Valve=%s, Pump=%s',
                masterSwitch.levelName,
                masterSwitch.levelName == 'Deszczówka' and 'deszczówka' or 'wodociąg',
                masterSwitch.levelName == 'Deszczówka' and 'On' or 'Off'),
                domoticz.LOG_WARNING)
            domoticz.log(string.format('  Actual: Valve=%s, Pump=%s',
                valve.levelName, pump.state),
                domoticz.LOG_WARNING)

            -- Always fix mismatch (could be after Domoticz restart or manual device change)
            domoticz.log('🔧 Correcting device mismatch...', domoticz.LOG_INFO)
            syncDevicesWithMaster(domoticz, masterSwitch, valve, pump)
            return -- Exit after fixing, wait for next cycle
        end

        -- === AUTOMATIC MODE ===
        if autoMode.state == 'Off' then
            domoticz.log('Auto mode disabled, no automatic switching', domoticz.LOG_DEBUG)
            return
        end

        -- Check if enough time has passed since last automatic switch
        local timeSinceLastSwitch = currentTime - domoticz.data.lastSwitchTime
        local canAutoSwitch = timeSinceLastSwitch >= MIN_SWITCH_INTERVAL

        if not canAutoSwitch then
            domoticz.log(string.format('⏳ Too soon for auto switch (%ds / %ds)',
                timeSinceLastSwitch, MIN_SWITCH_INTERVAL), domoticz.LOG_DEBUG)
        end

        -- === AUTOMATIC SWITCHING LOGIC ===

        -- Switch to TAP WATER when level too low
        if currentLevel <= MIN_LEVEL and masterSwitch.levelName == 'Deszczówka' then
            if canAutoSwitch then
                domoticz.log(string.format('═══ AUTO SWITCH: Rainwater → Tap Water (level %d%% ≤ %d%%) ═══',
                    currentLevel, MIN_LEVEL), domoticz.LOG_INFO)

                switchToTapWater(domoticz, masterSwitch, valve, pump)
                domoticz.data.lastSwitchTime = currentTime

                domoticz.notify('Rainwater Auto Switch',
                    string.format('Switched to TAP WATER - low level: %d%%', currentLevel),
                    domoticz.PRIORITY_NORMAL)
            else
                domoticz.log(string.format('⚠ Would switch to tap water (level %d%%) but interval too short',
                    currentLevel), domoticz.LOG_WARNING)
            end

        -- Switch to RAINWATER when level sufficient
        elseif currentLevel >= MAX_LEVEL and masterSwitch.levelName == 'Woda wodociągowa' then
            if canAutoSwitch then
                domoticz.log(string.format('═══ AUTO SWITCH: Tap Water → Rainwater (level %d%% ≥ %d%%) ═══',
                    currentLevel, MAX_LEVEL), domoticz.LOG_INFO)

                switchToRainwater(domoticz, masterSwitch, valve, pump)
                domoticz.data.lastSwitchTime = currentTime

                domoticz.notify('Rainwater Auto Switch',
                    string.format('Switched to RAINWATER - level: %d%%', currentLevel),
                    domoticz.PRIORITY_NORMAL)
            else
                domoticz.log(string.format('⚠ Would switch to rainwater (level %d%%) but interval too short',
                    currentLevel), domoticz.LOG_WARNING)
            end

        else
            -- No switching needed
            domoticz.log(string.format('✓ No action needed (level %d%%, thresholds: %d%%-%d%%)',
                currentLevel, MIN_LEVEL, MAX_LEVEL), domoticz.LOG_DEBUG)
        end
    end
}
