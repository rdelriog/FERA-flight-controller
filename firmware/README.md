# Firmware

| Folder | What | State |
|---|---|---|
| `px4/` | Git submodule → FERA fork of PX4-Autopilot (board `fera/core-v1`, module `fera_modules`, FERA airframes) | Not created yet |
| `esp32-bridge/` | ESP32 MAVLink-over-Wi-Fi bridge (ESP-IDF) | UART stub carried over from the starter repo |

## Next steps

1. In WSL2 Ubuntu: clone PX4-Autopilot, run `Tools/setup/ubuntu.sh`, confirm
   `make px4_sitl gz_x500` flies. PX4 does not build natively on Windows.
2. Fork PX4 under the FERA GitHub account and add it here as `firmware/px4`.
3. Add `src/modules/fera_modules` with a simulated EEPROM backend so the
   Configurator can be tested against SITL. Until a FERA MAVLink dialect
   exists, port status is streamed as `NAMED_VALUE_FLOAT` `FERA_P0`..`FERA_P3`
   (bits 0-7 module type, bit 8 latched, bit 9 present); the app already
   decodes this (`app/src/fera/spec.ts`).
4. Register the FERA airframes. The app currently assumes these
   `SYS_AUTOSTART` IDs (placeholders until registered in the fork):
   quad 4901, plane 2901, rover 50901, crawler 50902, boat 50903.
5. Board port `boards/fera/core-v1` from `hardware/fera-core/pinmap.md`.
