# FERA — Modular Drone

One central unit, five vehicles. The FERA hub (flight controller, battery,
four identical ports) becomes a quadcopter, fixed-wing plane, rover, crawler or
boat by swapping the plug-in modules. An app detects what is attached, selects
the operation mode and runs the pre-flight checks.

| Area | Path | What |
|---|---|---|
| Interface standard | [`docs/port-spec.md`](docs/port-spec.md) | The FERA Port: mechanics, latch, pinout, module ID |
| Mechanical | [`cad/`](cad/) | Parametric CAD (Python / build123d) → STEP + 3MF |
| Electronics | [`hardware/fera-core/`](hardware/fera-core/) | FERA Core flight controller (KiCad 8, STM32H743) |
| Firmware | [`firmware/`](firmware/) | PX4 board port + `fera_modules`, ESP32 MAVLink bridge |
| App | [`app/`](app/) | FERA Configurator (React + TypeScript, WebSerial; Tauri desktop) |
| BOMs | [`bom/`](bom/) | Electronics and mechanical bills of materials |
| Simulation | [`sim/`](sim/) | PX4 SITL / Gazebo per mode |
| Legacy | [`legacy/`](legacy/), [`hardware/legacy/`](hardware/legacy/) | Mark I KiCad board, 2021 Altium board, F7 firmware stub |

## Baseline

- Firmware: PX4 (one binary, mode = airframe + parameter pack)
- Size class: 5-inch, 4S LiPo, ~250 mm quad wheelbase
- MCU: STM32H743VIT6

## Quick start

```sh
# CAD: build all parts into cad/out/
python -m venv cad/.venv && cad/.venv/Scripts/pip install -r cad/requirements.txt
cad/.venv/Scripts/python cad/build.py

# App
cd app && npm install && npm run dev
```
