# FERA Port Specification — v0.1 (draft)

The FERA Port is the single interface between the central unit (hub) and every
interchangeable module: quad arm, wing, nose, tail, wheel drive, track, pontoon.
CAD (`cad/fera/port.py`), the FERA Core PCB and the PX4 `fera_modules` driver
all implement this document. Change it here first.

Status: **draft**. Items marked `TBD-P1` are frozen only after the Phase 1
coupon tests (section 7).

## 1. Principles

1. **Structure carries load, contacts carry current.** No flight, landing or
   crash load may pass through an electrical contact. The electrical connector
   floats; the socket taper does the alignment.
2. **One orientation.** A module cannot be inserted rotated or upside down.
3. **Positive, visible, sensed latch.** The user can see it is locked, and the
   firmware refuses to arm if it is not.
4. **Every module identifies itself.** No manual configuration of what is
   plugged in.
5. **All four ports are identical.** Any module type may define which ports it
   accepts, but the hub side never differs.

## 2. Port naming and vehicle frame

Hub body frame follows PX4 (X forward, Y right, Z down). Ports sit on the four
faces of the hub.

| Port | Index | Direction (hub frame) |
|---|---|---|
| FRONT | 0 | +X |
| RIGHT | 1 | +Y |
| BACK | 2 | −X |
| LEFT | 3 | −Y |

In **quad** mode the vehicle nose is declared between FRONT and RIGHT (hub yawed
45°, handled by the airframe's board rotation), giving a standard X quad. In all
other modes the nose is the FRONT port.

## 3. Mechanical interface

Parameters live in `cad/fera/port.py`; the values here are the nominal targets.

| Parameter | Value | Note |
|---|---|---|
| Structural member | 16 mm OD × 14 mm ID pultruded/roll-wrapped carbon tube | Common size, also used as wing spar |
| Module plug | Printed/machined collar bonded and pinned to the tube | Carries key, latch notch, connector carrier |
| Plug section | 24 mm square with 3 mm chamfers, one corner chamfered 6 mm as the key | Anti-rotation by the flats |
| Engagement length | 30 mm | ≥ 1.8 × tube OD |
| Draft / taper | 1° per side over the last 10 mm | Removes play when latched |
| Fit clearance (printed) | 0.30 mm per side, plus 0.20 mm on the bridged top flat | Socket only; the plug is nominal. 0.15 mm printed too tight to assemble. Fit gauge printed 2026-11-22 (Ender-3 Max Neo, PLA): all three sockets take the plug, 0.30 chosen as the slide-in fit with margin; the latch removes the remaining play. Tune per printer with the fit gauge (`port.fit_gauge()`, sockets at 0.20 / 0.30 / 0.40 mm) |
| Latch | Spring-loaded 4 × 35 mm steel dowel, 8 mm in from the port face, 3 mm into a pocket in the plug's top flat. A ramp on the plug lifts it on the way in, so it closes by itself; lift the knob 6 mm to release | Steel pin in printed bores; geometry in `cad/fera/latch.py` |
| Secondary retention | 2 mm pin through the knob skirt and its tower while latched | Required for flight modules |
| Latch sense | DRV5032AJ hall switch in the tower top, 2 × 1 mm magnet in the knob: about 39 mT latched, 1.1 mT lifted (switch on above 9.5 mT, off below 3 mT) | Open drain, low = latched, to LATCH0–3 on J14 |

Load targets (to be verified by test):

- Axial pull-out with latch closed: ≥ 150 N (≈ 5× max thrust of one motor: a 2212 920 KV on 4S with a 9-inch prop gives roughly 10–12 N, so 50–60 N; the 5-inch class it was first written for is ~60–75 N; target covers 2× safety on that).
- Bending at the socket: ≥ 6 N·m without permanent set (hard-landing case on a 125 mm arm).
- Torsion: ≥ 2 N·m (motor torque reaction plus wing pitching moment).
- No perceptible play at the motor mount after 500 insert/remove cycles.

## 4. Electrical interface

### 4.1 Power contacts

| Contact | Net | Rating target |
|---|---|---|
| P+ | VBAT (4S LiPo, 12.0–16.8 V) | 30 A continuous, 45 A for 10 s |
| P− | PWR_GND | same |

> **Datasheet check (Amass XT30PW-F spec V1.2):** 15 A rated, 30 A momentary,
> 0.8 mΩ contact resistance, 1000 mating cycles. That is half the 30 A
> continuous target above, so XT30PW only qualifies if the port rating is
> lowered to 15 A continuous / 30 A burst. FERA Core rev A is laid out and its
> current path is calculated for exactly that (15 A × 4 continuous, 30 A × 4
> burst). Polarity: the "+" contact is at the flat end of the housing.

Candidate connectors (`TBD-P1`): Amass **XT60PW** (board-mount, 30 A cont. /
60 A peak) as the baseline for margin; **MR30PW/XT30PW** as the compact option
if the temperature-rise test passes at 30 A.

Bulk capacitance for each ESC lives in the module, next to the ESC.

### 4.2 Signal contacts (8 positions)

Mating order: GND first, then power rails, then signals.

| Pin | Name | Direction (hub view) | Description |
|---|---|---|---|
| 1 | GND | — | Signal ground (first mate) |
| 2 | 5V | out | 5.0–5.3 V servo/logic rail, switched per port (TPS2069C: 1.5 A rated, limits at 1.7–2.5 A, off until the module ID is read). FERA Core rev A has one 3 A regulator behind all four switches (0.75 A per port on average); see `hardware/fera-core/audit.md` F3 |
| 3 | 3V3 | out | 3.3 V for ID EEPROM and sensors, 100 mA max. Shared by the four ports from their own current-limited LDO (250 mA total), not the hub's logic 3.3 V |
| 4 | S1 | out | ESC only: DShot (or ESC PWM). Never a servo |
| 5 | S2 | out | Servo PWM, 50 Hz |
| 6 | S3 | out | Servo PWM, 50 Hz |
| 7 | ID | bidir | 1-Wire, 2.2 kΩ pull-up to 3V3 on the hub, one bus per port |
| 8 | TELEM | in | ESC telemetry UART RX / module data (3.3 V logic) |

**Why S1 is ESC-only:** the autopilot sets protocol and update rate per
timer, and all four S1 pins share one timer (likewise S2, likewise S3). A servo
on any S1 would force every ESC off DShot. So a wing puts its aileron on S2 and
leaves S1 unconnected; a tail uses S2 (elevator) and S3 (rudder).

All signals are 3.3 V logic, with series resistors and ESD protection on the
hub side. Candidate connectors (`TBD-P1`): spring-loaded pogo pins (hub) on
ENIG pads (module ID PCB), or a floating board-to-board connector rated ≥ 1000
cycles.

### 4.3 Presence and latch

- **Module present** = ID EEPROM answers on the port's 1-Wire bus.
- **Latched** = latch-sense input closed.
- Arming requires: present AND latched on every port the selected mode needs,
  and no unexpected module type on any port.

## 5. Module identification (EEPROM)

Device: DS28E07 (1 kbit 1-Wire EEPROM, unique 64-bit ROM ID) or equivalent.
Little-endian, 32-byte record at offset 0:

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 4 | magic | `"FERA"` |
| 4 | 1 | schema | `1` |
| 5 | 1 | module_type | see table below |
| 6 | 1 | hw_rev | |
| 7 | 1 | allowed_ports | bitmask, bit n = port index n |
| 8 | 1 | s1_function | actuator function, see below |
| 9 | 1 | s2_function | |
| 10 | 1 | s3_function | |
| 11 | 1 | flags | bit0: motor spins CW; bit1: has ESC telemetry |
| 12 | 2 | s1_trim_us | signed, servo trim in µs |
| 14 | 2 | s2_trim_us | |
| 16 | 2 | s3_trim_us | |
| 18 | 4 | serial | |
| 22 | 8 | reserved | zero |
| 30 | 2 | crc16 | CRC-16/CCITT-FALSE over bytes 0–29 |

`module_type`:

| Value | Module |
|---|---|
| 0x00 | none / blank |
| 0x01 | quad arm (motor + ESC) |
| 0x10 | plane nose (motor + ESC) |
| 0x11 | plane wing, left |
| 0x12 | plane wing, right |
| 0x13 | plane tail (elevator + rudder) |
| 0x20 | wheel drive |
| 0x21 | track drive (crawler) |
| 0x30 | pontoon + thruster |
| 0x7F | blanking cap (closes an unused port, satisfies latch + ID) |

`sN_function`: 0 none, 1 motor, 2 aileron, 3 elevator, 4 rudder, 5 flap,
6 throttle (wheel/track/thruster), 7 steering. `s1_function` may only be 0, 1
or 6 (ESC-driven); the firmware rejects a module that declares otherwise.

## 6. Mode → required modules

| Mode | FRONT | RIGHT | BACK | LEFT |
|---|---|---|---|---|
| Quad | 0x01 | 0x01 | 0x01 | 0x01 |
| Plane | 0x10 | 0x12 | 0x13 | 0x11 |
| Rover | 0x20 or cap | 0x20 | 0x20 or cap | 0x20 |
| Crawler | cap | 0x21 | cap | 0x21 |
| Boat | cap | 0x30 | cap | 0x30 |

Unused ports must carry a blanking cap (keeps dust/water out and keeps the
"every port accounted for" rule simple).

## 7. Phase 1 qualification tests

Run on printed port coupons (`cad` target `port_coupon`) before freezing:

1. **Fit:** insertion force < 20 N, zero perceptible play when latched, on at
   least two different printers/materials.
2. **Pull / bend / torsion:** to the targets in section 3.
3. **Temperature rise:** 30 A for 10 min through the power contacts, < 30 °C
   rise at the contact.
4. **Vibration:** signal continuity logged at 1 kHz while a quad motor with a
   deliberately chipped prop runs at 50–100 % throttle for 5 min; zero dropouts.
5. **Cycle life:** 500 insert/latch/remove cycles, then repeat tests 1 and 4.
