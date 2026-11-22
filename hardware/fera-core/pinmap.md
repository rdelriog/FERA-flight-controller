# FERA Core rev A — MCU pin allocation (proposal)

MCU: **STM32H743VIT6** (LQFP-100). This table drives both the KiCad schematic
and the PX4 board files (`boards/fera/core-v1`), so they cannot drift apart.

> **Status:** every pin/function pair below is checked against the
> STM32H743VITx pin table in KiCad's symbol library each time the schematic is
> generated (`gen/make_schematic.py --check`, list in `design.MCU_FUNCS`), so
> each function exists on the pin shown. Alternate-function *numbers* (AF1,
> AF2, ...) and DMA/timer conflicts are still to be confirmed in STM32CubeMX.
> The netlist actually built into the board lives in `gen/design.py`; where
> the two differ, `design.py` is what was routed (see "Not on rev A
> preliminary" below).

## Design rules behind the allocation

1. **One timer per signal role, not per port.** PX4 sets protocol and rate per
   timer, so every port's S1 sits on the same timer (all ESCs: DShot), every S2
   on a second timer and every S3 on a third (servos: 50 Hz PWM). This is why
   the port spec reserves S1 for ESCs and S2/S3 for servos.
2. IMU on its own SPI bus with a data-ready interrupt.
3. Magnetometer is external (on the GPS mast), away from battery current.
4. Each port has its own 1-Wire ID line, so a shorted module cannot hide the
   others.

## Port signals

| Signal | Port 0 FRONT | Port 1 RIGHT | Port 2 BACK | Port 3 LEFT | Peripheral | ✔ |
|---|---|---|---|---|---|---|
| S1 (ESC, DShot) | PE9 | PE11 | PE13 | PE14 | TIM1 CH1–4 (AF1) | |
| S2 (servo PWM) | PD12 | PD13 | PD14 | PD15 | TIM4 CH1–4 (AF2) | |
| S3 (servo PWM) | PC6 | PC7 | PB0 | PB1 | TIM3 CH1–4 (AF2) | |
| ID (1-Wire) | PB5 | PA10 | PB2 | PC1 | GPIO open-drain, 2.2 kΩ pull-up; each on the MCU edge facing its port | |
| LATCH sense | PD3 | PD4 | PD7 | PD10 | GPIO input, pull-up, RC filter | |
| TELEM in | shared → PE0 | | | | UART8 RX (AF8). All four ports join here, each through its own 1 kΩ, so one shorted module cannot hold the line. A 4:1 mux is still deferred | |
| 5 V switch enable (high = on) | PE1 | PB12 | PE12 | PA2 | GPIO push-pull, 10 kΩ pull-down: off while the MCU is in reset | |
| 5 V switch fault (low = overcurrent) | PB4 | PD11 | PE10 | PA1 | GPIO input with pull-up; TPS2069C FLT is open-drain with a 9 ms deglitch | |

## Sensors and storage

| Function | Pins | Peripheral | ✔ |
|---|---|---|---|
| ICM-42688-P | PE2 SCK, PE5 MISO, PE6 MOSI, PE3 CS, PE4 DRDY | SPI4 (AF5) + EXTI4. These are MCU pins 1-5, the corner the IMU sits against, so the bus is under 10 mm long | |
| BMI270 (optional) / FRAM | PB13 SCK, PB14 MISO, PB15 MOSI, PB12 CS (IMU2), PD11 CS (FRAM) | SPI2 (AF5) | |
| DPS368 baro (0x76), INA226 (0x40), RGB LED driver | PB10 SCL, PB11 SDA | I2C2 (AF4) | |
| microSD | PC8–PC11 D0–D3, PC12 CK, PD2 CMD, PA8 card detect | SDMMC1 (AF12) | |

## External connectors

| Function | Pins | Peripheral | ✔ |
|---|---|---|---|
| GPS (JST-GH 6) | PB6 TX, PB7 RX | USART1 (AF7) | |
| External compass (on GPS connector) | PB8 SCL, PB9 SDA | I2C1 (AF4) | |
| TELEM1 → external ESP32 Wi-Fi bridge (JST-GH) | PD5 TX, PD6 RX | USART2 (AF7) | |
| RC receiver (CRSF / ELRS) | PD8 TX, PD9 RX | USART3 (AF7) | |
| Debug console | PE8 TX, PE7 RX | UART7 (AF7) | |
| CAN (reserved header) | PD0 RX, PD1 TX | FDCAN1 (AF9) | |
| USB-C | PA11 DM, PA12 DP, PA9 VBUS sense | USB OTG FS (AF10) | |
| SWD (Tag-Connect TC2030) | PA13 SWDIO, PA14 SWCLK, PB3 SWO, NRST | — | |

## Housekeeping

| Function | Pins | Notes | ✔ |
|---|---|---|---|
| HSE 16 MHz | PH0, PH1 | Crystal + load caps | |
| System rail (VSYS) sense | PC0 | ADC1 IN10, 10 k / 10 k divider + 100 nF | |
| Port 5 V switches | see port table | One TPS2069C per port (1.5 A, limit 1.7–2.5 A). Firmware enables a port after reading its module ID | |
| Port 3.3 V | — | Own LP5907 (3V3P, 250 mA, current-limited), not the MCU's 3V3 | |
| Buzzer | PA0 | TIM2 CH1 (AF1) | |
| Status LEDs (red / green / blue) | PC13, PC14, PC15 | Low-current GPIO only | |
| Safety / arm button | PA15 | Button to ground, internal pull-up | |
| BOOT0 | BOOT0 | 10 kΩ pull-down + test pad | |
| Spare | PA3, PA5, PA6, PA4 (not 5 V tolerant), PA7 (SPI1 free for a second IMU), PC2, PC3, PC4, PC5, PE15 | Bring out on test pads | |

## Checked against datasheets

| Part | Source | Result |
|---|---|---|
| ICM-42688-P | TDK DS-000347 rev 1.2, table 9 and figure 4 | Pin-out as used. Pin 7 must be grounded; pin 9 (INT2/FSYNC/CLKIN) is now grounded as the datasheet asks when FSYNC is unused (it was left open before). Decoupling changed to the datasheet values: 100 nF + 2.2 µF on VDD, 10 nF on VDDIO. KiCad's LGA-14 footprint matches the datasheet's top view |
| DPS310 / DPS368 | Infineon pin table | 1 GND, 2 CSB, 3 SDI, 4 SCK, 5 SDO, 6 VDDIO, 7 GND, 8 VDD as used; SDO low gives I2C address 0x76 |
| XT30PW-F | Amass spec V1.2 drawing | "+" is the contact at the flat end = pad 2 of KiCad's footprint. The first layout had VBAT on pad 1: reversed, now fixed |
| INA226, LMR33630, TLV62569, LP5907, USBLC6, microSD, USB-C, Tag-Connect | KiCad library symbols | Every net checked against the library pin name by `gen/make_schematic.py --check` (table in `gen/pin_check.txt`) |

## Mark I mistakes this board must not repeat

- VDD pins on their own 3V3 net (Mark I tied them to VBAT), VBAT separate.
- VCAP1/VCAP2 each with 2.2 µF to ground.
- NRST with 100 nF and a pull-up; SWD brought out.
- Crystal fitted; USB-C CC1/CC2 each with 5.1 kΩ to ground.
- No motor current through signal connectors or through thin traces.

## Not on the rev A preliminary layout

Second IMU (BMI270), FRAM, CAN transceiver, ESC-telemetry mux, port 5 V load
switch (PE15), buzzer driver (PA0 is on a test pad), RGB LED driver, series and
ESD protection on the port signals, reverse-polarity protection (the battery
input TVS is fitted: D5).
