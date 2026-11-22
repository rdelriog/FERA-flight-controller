# Firmware

| Folder | What | State |
|---|---|---|
| `px4/` | PX4 board port `boards/fera/core-v1` (master copy; copy into a PX4 v1.17 tree to build) and `check_pins.py` | Builds: firmware and bootloader. Not run on hardware. See `px4/README.md` |
| `esp32-bridge/` | ESP32 MAVLink-over-Wi-Fi bridge (ESP-IDF) | UART stub carried over from the starter repo |

## Next steps

1. Done (2026-11-22): PX4 v1.17.0 cloned in WSL Ubuntu at `~/PX4-Autopilot`, toolchain
   installed, `fera_core-v1` builds. Simulation tools (Gazebo) are not installed yet.
2. Later: fork PX4 under the FERA GitHub account and move the board folder there.
3. Add `src/modules/fera_modules` with a simulated EEPROM backend so the
   Configurator can be tested against SITL. Until a FERA MAVLink dialect
   exists, port status is streamed as `NAMED_VALUE_FLOAT` `FERA_P0`..`FERA_P3`
   (bits 0-7 module type, bit 8 latched, bit 9 present); the app already
   decodes this (`app/src/fera/spec.ts`).
4. Register the FERA airframes. The app currently assumes these
   `SYS_AUTOSTART` IDs (placeholders until registered in the fork):
   quad 4901, plane 2901, rover 50901, crawler 50902, boat 50903.
5. Done: board port `boards/fera/core-v1` from `hardware/fera-core/pinmap.md` (see `px4/README.md`).
