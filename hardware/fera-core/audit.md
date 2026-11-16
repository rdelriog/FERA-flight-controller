# FERA Core rev A — independent schematic audit

A second model (Claude Opus, fresh context, read-only) reviewed the circuit in
`gen/design.py` against the TI datasheets for the LMR33630, TLV62569, INA226 and LP5907,
which it opened. It could not download the STM32H743 datasheet, so its STM32 statements
are from memory. This file records each finding and what was done about it.

Verdict of the audit: **not ready for fabrication**: one error, eleven warnings, seven
suggestions. The error and most warnings are fixed below; the open ones are listed last.

## Fixed in the design

| # | Finding | What changed |
|---|---|---|
| F1 (error) | On USB alone, D1 fed the 5 V rail, and the 5 V buck's high-side FET conducted backwards into VBAT: USB would charge the battery-side capacitors and every ESC, and a servo could overload the USB port | New system rail **VSYS** = 5 V through D6 (SS34) or USB through D1. VSYS feeds the 3.3 V buck, the sensor LDO, the GPS / TELEM / RC connectors and the 5 V sense divider. The ports' 5 V rail is fed by the buck only, so USB can no longer reach the buck output, the battery or the servos |
| F2 | USB_VBUS floated when unplugged, so PA9 could read "USB connected" on battery | R23 10 k from USB_VBUS to GND |
| F3 (part) | Servos can push energy back into the 5 V rail; nothing absorbed or clamped it | C31 220 µF bulk and D7 SMAJ5.0A clamp on the 5 V port rail. D6 also keeps that rail one diode away from the 6 V-limit parts on VSYS |
| F5 | 5 V buck output capacitance below TI's figure for 5 V at 400 kHz | C22, C23 changed to 22 µF 16 V 1210 and C34 added (3 × 22 µF), plus the 220 µF bulk. TI's table uses 4 × 22 µF: there was no room for the fourth at the inductor |
| F6 (part) | 5 V buck input capacitor too small after DC bias and too far away | C30 is now 10 µF 50 V directly under the VIN / PGND pins; C21 is 10 µF 50 V. The separate 220 nF high-frequency capacitor TI asks for is not fitted (no room at the pins) |
| F7 | Inductor saturation current not specified | L1 note: saturation current at least 5.1 A; part still to be chosen |
| F8 | LP5907 capacitors below 0.7 µF effective | C17, C18 changed to 2.2 µF |
| F10 (part) | ESC_TELEM floated with no ESC fitted | R24 10 k pull-up to 3V3 |
| F12 | P2_ID was on PA4, which is not 5 V tolerant | Moved to PB2 |
| F13 | 3.3 V buck: inductor would saturate at the switch limit, no feed-forward capacitor, small input capacitor | L2 changed to a 4 × 4 mm part (XAL4020-222 class), C35 6.8 pF across R9, C26 now 10 µF 0805 |
| F15 | Crystal load capacitance unspecified | Y1 specified as CL 8 pF, ESR 80 Ω or less, matching the 10 pF capacitors |
| F16 | Green and blue LEDs too dim through 1 k | R14 680 Ω, R15 and R16 330 Ω (still under the 3 mA the PC13–15 pins may sink) |
| F17 (part) | PX4's INA226 driver defaults to a different address | Noted on U4: start the driver with `-a 0x40` |
| F18 (part) | No capacitor on the 5 V sense ADC input | C32 100 nF on V5_SENSE |
| F19 (part) | No capacitor on VBUS at the connector | C33 1 µF on USB_VBUS |

## Still open

| # | Finding | Why it is open |
|---|---|---|
| F3 | The 5 V buck is 3 A, but `docs/port-spec.md` allowed 1.5 A of 5 V per port (6 A). A servo stall still browns out the 5 V port rail | Needs a decision: a second regulator for the servo rail, a BEC in each module, or a lower figure in the spec. The spec now states the 3 A total |
| F4 | 5 V and 3V3 go to the port contacts with no current limit; a shorted module or a pin touching during insertion lands on the MCU's own 3V3 | Needs a load switch per port (planned, PE15) and a current-limited 3V3 feed; not placed yet |
| F9 | No reverse-polarity protection; the SMBJ18A is small for regenerative dumps from four ESCs | Known gap; an ideal-diode stage and a larger TVS do not fit the battery corner as laid out |
| F10 | ESC_TELEM is one net across four ports: one bad module kills telemetry from all | Needs the deferred 4:1 mux or a series resistor per port |
| F11 | Port signals go from MCU pins straight to the contacts: no series resistors, no ESD parts | Known gap |
| F14 | No pull-ups on the microSD lines, no bulk capacitor at the socket | PX4/NuttX enables the MCU's internal pull-ups on the SDMMC pins (to be confirmed in the board port); external 47 k and a 10 µF are not fitted |
| F17 | Optional INA226 input filter | Not fitted |
| F18 | VBAT pin has no capacitor of its own; IMU chip-select has no pull-up; the latch inputs have no RC filter | Not fitted; debounce the latch inputs in software |
| F19 | USB shield tied straight to ground; no VBUS TVS | Accepted for rev A |

## Things the audit could not verify

- Everything about the STM32H743 itself (pin voltage tolerance, the PC13–15 sink limit,
  VCAP and VBAT capacitor requirements, crystal drive margin): recalled, not read.
- The inductor and Schottky ratings, PX4's INA226 default address, whether BLHeli_32 / AM32
  ESCs release the telemetry line between frames, the microSD detect-switch polarity.
- Capacitor voltage ratings and dielectrics where `design.py` gives none.
- Anything that depends on the layout rather than the circuit.

## Checked and found correct by the audit

LMR33630 pin-out, feedback divider (5.02 V), boot and VCC capacitors, EN and PG handling;
TLV62569 pin-out and divider (3.32 V); LP5907 pin-out; INA226 pin-out, address, common-mode
range and Kelvin connection; USB-C CC resistors, ESD part connection and diode orientation;
STM32 decoupling, VCAP, VDDA filter, BOOT0, NRST; sensor decoupling and addresses; the I2C
pull-ups on 3V3 with sensors on 3V3S; the Pixhawk-style connector pin-outs and the Tag-Connect
pin-out; 1-Wire pull-ups; power sequencing.
