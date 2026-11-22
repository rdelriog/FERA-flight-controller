# PX4 board port: `fera/core-v1`

PX4 board files for the FERA Core rev A flight controller (`hardware/fera-core`). Built
against **PX4 v1.17.0**. This folder is the master copy. To build, copy it into a PX4 tree.

## Build

In WSL Ubuntu (PX4 does not build natively on Windows), with PX4 cloned at `~/PX4-Autopilot`
and its toolchain installed (`Tools/setup/ubuntu.sh --no-sim-tools`):

```sh
cp -r /mnt/c/FERA/modular-drone-starter/firmware/px4/boards/fera ~/PX4-Autopilot/boards/
cd ~/PX4-Autopilot
make fera_core-v1_bootloader      # build/fera_core-v1_bootloader/fera_core-v1_bootloader.bin
make fera_core-v1_default         # build/fera_core-v1_default/fera_core-v1_default.px4
```

Check the board files against the PCB design (run from the FERA repo):

```sh
python firmware/px4/check_pins.py
```

Last build (2026-11-22, Ubuntu's arm-none-eabi-gcc 14.2.1):
- **Firmware:** 1.52 MB, 77 % of the 1.92 MB application flash.
- **Bootloader:** 41 KB.
- **Warnings:** none from the board files.

## First flash (new board)

1. Bootloader over SWD: write `fera_core-v1_bootloader.bin` at `0x08000000` with an ST-Link
   on the Tag-Connect footprint, e.g. `st-flash write fera_core-v1_bootloader.bin 0x08000000`.
   The firmware build also copies it into `boards/fera/core-v1/extras/` (git-ignored, like
   every `.bin`).
2. Firmware over USB: QGroundControl > Vehicle Setup > Firmware > Advanced > custom file,
   choose `fera_core-v1_default.px4`. Or from WSL:
   `make fera_core-v1_default upload` (USB passed through with `usbipd`).

## What the port sets up

| Function | Hardware | PX4 |
|---|---|---|
| Clock | 16 MHz crystal | SYSCLK 480 MHz (PLL1 /2 x120 /2), USB 48 MHz from PLL3 |
| IMU | ICM-42688-P on SPI4 (CS PE3, DRDY PE4) | `icm42688p -s -b 4` |
| Barometer | DPS368 on I2C2, 0x76 | `dps310 -I -b 2` (register-compatible) |
| Battery | INA226 on I2C2, 0x40, 0.2 mOhm shunt | `ina226 -I -b 2 -t 1`, `INA226_SHUNT 0.0002` |
| Compass | External, on the GPS connector (I2C1) | Probed by PX4's normal external-sensor start-up |
| Outputs 1-4 | S1 of ports FRONT, RIGHT, BACK, LEFT: TIM1 (DMA) | ESCs, DShot |
| Outputs 5-8 | S2 of the four ports: TIM4 | Servos, PWM |
| Outputs 9-12 | S3 of the four ports: TIM3 | Servos, PWM |
| `/dev/ttyS0` | USART1, GPS connector | GPS1 |
| `/dev/ttyS1` | USART2, TELEM1 (ESP32 bridge) | MAVLink, 921600 |
| `/dev/ttyS2` | USART3, RC connector | RC input (CRSF / ELRS) |
| `/dev/ttyS3` | UART7 | NuttX console (57600) |
| `/dev/ttyS4` | UART8 RX, shared ESC telemetry | `DSHOT_TEL_CFG` = EXT2 |
| microSD | SDMMC1, card detect PA8 | Logs, parameters |
| USB | OTG FS, VBUS sense PA9 | MAVLink / NSH, ID 1B8C:0036 "FERA Core" |
| Port GPIO | 5 V enable, fault, latch, 1-Wire ID per port | Defined in `board_config.h`; enables are held low at boot and on every reset |
| HRT | TIM5 (no pin) | |
| Tone alarm | PA0, TIM2 CH1 | Test pad only on rev A |
| Board ID | | 7300 (unregistered, pick a free one before any release) |

## Not done / to check on the first board

- **IMU rotation:** `-R 0` (none) until the sensor's orientation on the assembled board is
  confirmed. Check with the vehicle level and the `sensor_accel` topic.
- **Safety button:** PA15 reads low when pressed. PX4's `safety_button` driver expects high,
  so it is not built. Arming works from the RC transmitter.
- **LEDs and buzzer:** on test pads only on rev A. LED polarity is assumed active high.
- **FERA port logic:**
  - The board only holds every port's 5 V off. Nothing turns a port on yet.
  - Nothing yet reads the module ID EEPROMs or the latch sensors, and nothing blocks arming.
  - That is the planned `fera_modules` module. Until it exists, turn a port on by hand from
    the NSH console, e.g. `gpio write E1 1` for port 0 (B12, E12, A2 for ports 1–3). That bypasses the ID check, so do it
    only with a known module plugged in.
- **ROS 2 bridge left out:** the `uxrce_dds_client` module is not built. It does not compile
  with GCC 14. PX4's recommended GCC 13.2 would build it, but FERA does not use it.
- **USB ID:** 1B8C:0036 is the generic ID many PX4 hobby boards share, so QGroundControl
  recognises it.
- **Not run on hardware:** nothing here has run yet, because no board has been built. It
  compiles, and every pin is checked against the PCB design by `check_pins.py`.
