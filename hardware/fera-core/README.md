# FERA Core rev A — preliminary board and schematic

The flight controller and power distribution board that sits in the hub
between the four ports. **Preliminary design: for review, not for fabrication.**

| File | What |
|---|---|
| `fera-core.kicad_pro` | Open this in KiCad 8: schematic and board together |
| `fera-core.kicad_sch` + `mcu`, `sensors`, `power`, `io`, `ports` `.kicad_sch` | The schematic: an overview page and five pages. Generated — see below |
| `fera-core.kicad_pcb` | The board. Generated — see below |
| `fera.kicad_sym`, `fera.pretty/` | Project symbols (IMU, barometer, XT30) and the Kelvin shunt footprint |
| `pinmap.md` | MCU pin allocation, the reasoning behind it, and what was checked against datasheets |
| `audit.md` | Independent review of the circuit: every finding, what was fixed, what is still open |
| `gen/design.py` | **Source of truth**: parts, values, nets, placement, outline, copper, rules |
| `gen/make_schematic.py` | Writes the schematic from `design.py`; `--check` runs ERC and compares the netlist |
| `gen/build_board.py` | Builds the board from `design.py` with KiCad's Python API |
| `gen/router.py` | Small grid autorouter used for the preliminary routing |
| `gen/check_board.py` | KiCad DRC incl. schematic parity, signal length/impedance report, PDF plots |
| `gen/power_check.py` | Current calculation of the battery path on the board's real copper |
| `gen/mcu_pins.py`, `gen/ids.py` | STM32 pin table from KiCad's library; UUIDs shared by schematic and board |
| `plots/` | PDFs of the schematic and the layers, `power_density.png` |

## Regenerating

```sh
cd hardware/fera-core
KPY="C:/Program Files/KiCad/8.0/bin/python.exe"
VPY=../../cad/.venv/Scripts/python
python gen/make_schematic.py --check     # schematic + ERC + netlist comparison
$KPY gen/build_board.py --dump-pads      # placement check, pad geometry -> gen/pads.json
$VPY gen/escape_test.py                  # 10 s: is any pad walled in by the fixed copper?
$VPY gen/preview.py                      # route (10-15 min) -> gen/route_result.json, preview.png
$KPY gen/build_board.py --use-result     # tracks, vias, planes, pours, stack-up, net classes
python gen/check_board.py                # DRC, schematic parity, signal report, plots
$KPY gen/build_board.py --dump-copper    # filled copper -> gen/copper.json
$VPY gen/power_check.py                  # battery-path current calculation
python gen/make_bom.py                   # ../../bom/fera-core-revA.csv
```

`$VPY gen/preview.py --quick` routes only the plane vias and the frozen nets (1 s); that is
enough for `power_check.py` when only the power copper changed.

The schematic and the board are both overwritten on every run, so **make changes in
`gen/design.py`, not in KiCad**, until the design is taken over by hand. Once you start
editing in KiCad, stop regenerating. The footprints carry the UUIDs of their schematic
symbols, so KiCad's *Update PCB from Schematic* works on the files as they are.

## The schematic

Every pin has a short wire and a net label, and power pins have power symbols, so nets are
joined by name rather than by drawn wires. It is a complete, ERC-clean picture of the netlist,
not a hand-drawn schematic: fine for review and for driving the board, worth redrawing by
hand page by page later. Symbols come from KiCad's libraries wherever one exists
(STM32H743, INA226, LMR33630, TLV62569, LP5907, USBLC6, USB-C, microSD, Tag-Connect), which
lets `--check` compare every net against the library's pin names.

## What is on the board

- STM32H743VIT6, 16 MHz crystal, decoupling under the chip, SWD (Tag-Connect TC2030)
- ICM-42688-P IMU on SPI4, against the MCU corner that carries SPI4; DPS368 barometer;
  both on their own low-noise 3.3 V rail
- Battery input pads, 0.2 mΩ shunt with Kelvin sense pads + INA226, TVS clamp
- 5 V buck (LMR33630) for the ports' 5 V rail, with bulk capacitor and clamp
- System rail VSYS (5 V or USB through two diodes) feeding the 3.3 V buck (TLV62569), the
  sensor LDO and the GPS / TELEM / RC connectors, so USB cannot back-feed the battery side
- Four ports, each with a power connector and an 8-way signal connector, and per port: a
  TPS2069C current-limited switch for the module's 5 V (enable and fault to the MCU),
  100 Ω in series with S1–S3 and ID, 1 kΩ in the shared telemetry line and a USBLC6-4 clamp
  on the contact side. Port 3.3 V has its own current-limited LDO (3V3P)
- USB-C with ESD protection, microSD, GPS / TELEM1 / RC / latch-sense connectors
- Safety button, three status LEDs, test pads (BOOT0, debug UART, buzzer)

## Board shape

The outline is driven by the hub: a 56 mm central square between the four
socket blocks, four lobes in the hub's free corners, and a tongue that carries
the USB-C connector to the hub wall. `cad/build.py` checks that this outline
fits inside the printed hub and places the standoffs under the mounting holes.

## Stack-up (6 layers, 1.6 mm)

| Layer | Copper | Use |
|---|---|---|
| F.Cu | 1 oz | Components, signals, ground fill, battery pours |
| In1 | 2 oz | GND plane (carries the motor return current) |
| In2 | 2 oz | 3V3 fill, also carries slow signals (0.2 mm tracks, 0.2 mm gaps) |
| In3 | 2 oz | VBAT plane (battery current to the four ports) |
| In4 | 2 oz | 5V plane |
| B.Cu | 1 oz | Decoupling, signals, ground fill |

Nets with a plane are not routed pad to pad: each surface pad gets a short stub
and a via. The router may also put slow signals (GPIO, UARTs, I2C, port lines) on In2; the
fast and sensitive nets (USB, SD, IMU, crystal, buck nodes, current sense) stay on the outer
layers over a solid plane. Where In2 tracks fence off a piece of the 3V3 fill, the router
joins that piece's vias back with a short outer-layer track (`stitch_plane` in `router.py`). The dielectric thicknesses in the board file are a typical build
(0.11 mm prepreg under the outer layers); the fabricator's own stack-up replaces them.

## Status (measured on the generated files)

| Check | Result |
|---|---|
| Schematic ERC (KiCad 8) | 0 errors, 0 warnings |
| Schematic netlist vs `design.py` | 501 pin-to-net assignments, 0 differences |
| Independent circuit review | Done, see `audit.md`. Its error and most warnings are fixed, including port protection; still open: 5 V budget, reverse polarity, telemetry mux and some optional parts |
| MCU functions vs KiCad's STM32H743 pin table | 44 of 44 on a pin that offers them |
| Schematic ↔ board parity (KiCad DRC) | 0 issues |
| Placement | 132 parts + 4 mounting holes, no courtyard overlaps, all inside the outline |
| Routing | 202 of 202 signal connections; every plane pad has its via |
| Board DRC | 0 errors, 0 unconnected items; about 140 silkscreen warnings (cosmetic). The stock USB-C footprint's ground pads sit 0.19 mm from its locating holes: allowed for that footprint only in `fera-core.kicad_dru` (0.25 mm everywhere else); confirm the fab accepts it |

The router's result depends on routing order, so a different placement can leave a
connection open; it ends with a repair pass that moves only the tracks in the way, and
`check_board.py` reports anything left.

### Battery path (`gen/power_check.py`)

Path: BAT+ pad → pour on top, bottom and an island in the VBAT layer → 0.2 mΩ shunt →
via field → 2 oz VBAT plane → port "+" pads, and back through the 2 oz GND plane to the BAT−
pad. Copper at about 70 °C, outer-layer ground fills ignored (pessimistic).

| Load | Board copper + shunt | of which shunt | Drop, battery pads to worst port (+ and −) | Connector contacts (8 × 0.8 mΩ) |
|---|---|---|---|---|
| 4 × 15 A = 60 A (XT30 continuous rating) | 6.1 W | 0.7 W | 77 mV + 32 mV | 1.4 W |
| 4 × 30 A = 120 A (XT30 momentary rating) | 24 W | 2.9 W | 154 mV + 63 mV | 5.8 W |

Loss scales with the square of the current: about 0.7 W at a 20 A hover and 2.7 W at 40 A.
Where the 6.0 W goes at 60 A: VBAT plane 2.0 W, GND plane 1.6 W, top-layer copper next to
the shunt pads 1.3 W, shunt 0.7 W, vias 0.3 W. The hottest spots are the 1 oz copper at the
two shunt pads and the three large vias beside the shunt (up to 9 A each at 60 A, 18 A at
120 A); `plots/power_density.png` shows them. 60 A continuous in still air would run the
board roughly 50 K above ambient, so that figure needs airflow or a lower rating; the
120 A case is a few-seconds burst.

What the calculation changed: the first via field sat in the 11 × 11 mm neck where the
battery lobe joins the board and nearly cut every plane there (7.8 W at 60 A). The neck is
now a no-via area, BAT− and the via field sit either side of it, and the buck's output
vias moved out of it.

### Signals (`gen/check_board.py`)

0.15 mm tracks over the 0.11 mm prepreg are about 56 Ω single-ended; a 0.15/0.15 mm pair is
about 97 Ω (USB wants 90 Ω ± 15 %). Confirm with the fabricator's stack-up.

| Group | Longest | Spread | Notes |
|---|---|---|---|
| IMU SPI4 (≤ 24 MHz) | 21.5 mm | 17.7 mm (105 ps) | SCK and CS 3.8 mm with no vias; MISO now detours (21.5 mm, 4 vias). Still short for 24 MHz |
| USB full speed, MCU to ESD part | 42.6 mm | 0.1 mm (1 ps) | D+ 2 vias, D− 0. Not a coupled pair: fine for 12 Mbit/s, re-route with KiCad's pair router (net class `USB`) if you want it tidy |
| USB, ESD part to connector | 5.7 mm | 0.5 mm | Frozen before anything else is routed |
| microSD SDMMC1 (≤ 50 MHz) | 45.4 mm | 9.4 mm (56 ps) | Routed first, 2 vias per line (the previous run had a 114 mm SD_CMD detour) |
| Crystal | 5.1 mm | — | No vias; other nets are kept out of its area on the top layer |
| Current-sense pair | 8.6 mm | 0.1 mm | From the shunt's own sense pads |

All of these are electrically short for their edge rates as long as the GPIO slew rate is set
to medium, so none needs length tuning. Top-layer signals run over the GND plane;
bottom-layer signals run over the 5 V plane.

## Known gaps before this can be fabricated

- **Open audit findings** (`audit.md`): the 5 V regulator is 3 A for all four ports (each
  port is now limited to 1.7–2.5 A, but four together can still exceed 3 A), there is no
  reverse-polarity protection, and ESC telemetry from all ports shares one UART.
- **The schematic is generated, not drawn.** It matches the board by construction and by
  check, and the circuit has now had one independent review, but that review could not
  read the STM32H743 datasheet and nothing has been simulated or built.
- **Port current rating.** XT30PW-F is 15 A continuous / 30 A momentary per the Amass
  spec; `docs/port-spec.md` asks for 30 A continuous. Either the spec comes down or the
  connector goes up (XT60PW) after the Phase 1 tests. The port connectors here are
  placeholders in any case (XT30 + 2x4 1.27 mm header).
- **Battery path.** Numbers above. The 1 oz copper at the shunt pads is the weak point;
  filled via-in-pad or a wider shunt package would fix it. The shunt part number is not chosen.
- **Not checked against a datasheet drawing:** the DPS368 land pattern (pin-out is checked),
  and the XT30 polarity was read from the Amass drawing and KiCad's footprint, not from a
  part: check with a meter on the first connector.
- **Buck converters:** placed by the datasheet rules (input capacitor under VIN/PGND,
  inductor at SW, thermal vias) but not simulated. The 5 V buck has three of the four
  22 µF output capacitors TI's table lists and no separate 220 nF input capacitor.
- **System rail routing:** VSYS is a 0.4 mm track about 190 mm long linking three corners
  of the board; fine for the 1 A it carries, but it should become a pour or a wider track
  when the board is routed by hand.
- Left off deliberately: second IMU, FRAM, CAN, ESC-telemetry mux, buzzer driver,
  RGB LED driver.
