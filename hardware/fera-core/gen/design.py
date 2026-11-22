"""FERA Core rev A — design data: parts, nets, placement, outline, copper rules.

Pure data, no KiCad imports. Coordinates are millimetres relative to the board
centre in KiCad's screen frame (X right, Y down). The FRONT port is at the top
(-Y), RIGHT at +X, BACK at +Y, LEFT at -X.

This file is the single source for both generators:
    make_schematic.py  ->  fera-core.kicad_sch (+ one sheet per section)
    build_board.py     ->  fera-core.kicad_pcb
"""
import math

# ---------------------------------------------------------------------------
# Board outline: central 56 x 56 mm square between the four socket blocks,
# four corner lobes in the hub's free diagonal space, and a tongue carrying
# the USB-C connector out to the hub wall.
# ---------------------------------------------------------------------------
HALF = 28.0          # central square half-size (hub socket blocks start at 29)
LOBE_IN = 17.0       # lobes start 1 mm outside the 32 mm wide socket blocks
LOBE_OUT = 44.0
CHAMFER = 75.0       # |x| + |y| limit: keeps clear of the hub's lid bosses
TONGUE_X = 57.0
TONGUE_Y = 29.5

_c = CHAMFER - LOBE_OUT   # 31
OUTLINE = [
    (-LOBE_IN, -HALF), (LOBE_IN, -HALF),                                   # FRONT edge
    (LOBE_IN, -LOBE_OUT), (_c, -LOBE_OUT), (LOBE_OUT, -_c),                # front-right lobe
    (LOBE_OUT, -TONGUE_Y), (TONGUE_X - 2, -TONGUE_Y), (TONGUE_X, -TONGUE_Y + 2),
    (TONGUE_X, -LOBE_IN), (HALF, -LOBE_IN),                                # USB tongue
    (HALF, LOBE_IN),                                                       # RIGHT edge
    (LOBE_OUT, LOBE_IN), (LOBE_OUT, _c), (_c, LOBE_OUT), (LOBE_IN, LOBE_OUT), (LOBE_IN, HALF),
    (-LOBE_IN, HALF),                                                      # BACK edge
    (-LOBE_IN, LOBE_OUT), (-_c, LOBE_OUT), (-LOBE_OUT, _c), (-LOBE_OUT, LOBE_IN), (-HALF, LOBE_IN),
    (-HALF, -LOBE_IN),                                                     # LEFT edge
    (-LOBE_OUT, -LOBE_IN), (-LOBE_OUT, -_c), (-_c, -LOBE_OUT), (-LOBE_IN, -LOBE_OUT),
]

MOUNT_HOLES = [(21.5, -39.5), (21.5, 39.5), (-21.5, 39.5), (-21.5, -39.5)]

# ---------------------------------------------------------------------------
# Stack-up and rules
# ---------------------------------------------------------------------------
# 6 layers: F signal / GND / 3V3 fill + slow signals / VBAT / 5V / B signal
# (GND is also poured on F and B)
PLANES = {"GND": ["In1.Cu"], "3V3": ["In2.Cu"], "VBAT": ["In3.Cu"], "5V": ["In4.Cu"]}

# Layers the router may put tracks on. In2 is the 3V3 fill: slow nets may cross it, the fill
# closes around them. It is 2 oz copper, so its tracks and gaps are 0.2 mm.
ROUTE_LAYERS = ["F", "B", "In2.Cu"]
LAYER_RULES = {"In2.Cu": dict(track=0.2, clearance=0.2)}
# Nets that stay on the outer layers, each directly over a solid plane: the fast buses, the
# crystal, the switching nodes and the current-sense pair.
OUTER_ONLY = ("USB_", "SD_", "IMU_", "OSC_", "BUCK_", "ISNS_", "V3_")


def inner_ok(net):
    return not net.startswith(OUTER_ONLY)


# Copper thickness in mm per layer and the dielectric between layers (top to bottom).
# Inner layers are 2 oz because In1 (GND) and In3 (VBAT) carry the motor current.
# The prepreg/core split is a typical 1.6 mm build; the fab's own stack-up replaces it.
COPPER_MM = {"F.Cu": 0.035, "In1.Cu": 0.070, "In2.Cu": 0.070, "In3.Cu": 0.070, "In4.Cu": 0.070,
             "B.Cu": 0.035}
DIELECTRIC_MM = [("prepreg", 0.11), ("core", 0.45), ("prepreg", 0.13), ("core", 0.45),
                 ("prepreg", 0.11)]
EPSILON_R = 4.2

CLEARANCE = 0.15
TRACK = 0.15
VIA_DIA, VIA_DRILL = 0.6, 0.3
PWR_VIA = (0.8, 0.4)                 # diameter, drill of the battery-current vias
BIG_VIA = (1.3, 0.8)                 # the ones right against the shunt pad
WIDTHS = {          # track width per net (default TRACK)
    "5V": 0.4, "VSYS": 0.4, "BUCK_SW": 0.6, "V3_SW": 0.5, "USB_VBUS": 0.4,
    "3V3S": 0.25, "3V3A": 0.25, "VCAP1": 0.25, "VCAP2": 0.25, "BUCK_BOOT": 0.2, "BUCK_VCC": 0.2,
    "GND": 0.25, "3V3": 0.25, "VBAT": 0.4, "VBAT_IN": 0.4, "3V3P": 0.25,
    **{f"P{p}_5V": 0.4 for p in range(4)},
}

# KiCad net classes written into the project file (name -> settings and member nets).
# Net names ending in _P / _N are recognised by KiCad as a differential pair.
NETCLASSES = {
    "USB": dict(track=0.15, clearance=0.15, dp_width=0.15, dp_gap=0.15,
                nets=["USB_D_P", "USB_D_N", "USB_CONN_D_P", "USB_CONN_D_N"]),
    "Power": dict(track=0.4, clearance=0.15, nets=["VBAT", "VBAT_IN", "5V", "VSYS", "BUCK_SW", "V3_SW",
                                                    "USB_VBUS", "P0_5V", "P1_5V", "P2_5V", "P3_5V"]),
    "Sense": dict(track=0.15, clearance=0.15, dp_width=0.15, dp_gap=0.15,
                  nets=["ISNS_P", "ISNS_N"]),
}

# Nets routed first and then frozen (never ripped up): the crystal, the buck's hot loop,
# the current-sense pair and the USB pair. Order matters.
PRE_ROUTE = ["OSC_IN", "OSC_OUT", "BUCK_SW", "BUCK_BOOT", "BUCK_VCC", "BUCK_FB",
             "ISNS_N", "ISNS_P", "USB_CONN_D_P", "USB_CONN_D_N"]

# Nets the router should place before the rest: ones whose pads are easy to wall in
# (connector end pins) or that cross the whole board.
ROUTE_FIRST = ["USB_D_P", "USB_D_N", "SD_CK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3",
               "IMU_SCK", "IMU_CS", "IMU_MISO", "IMU_MOSI", "IMU_DRDY",
               *[f"P{p}_{s}" for p in (1, 0, 2, 3) for s in ("S3", "S2", "S1", "ID")],
               *[f"P{p}_5V" for p in range(4)],
               *[f"P{p}_{s}_C" for p in range(4) for s in ("S1", "S2", "S3", "ID", "TELEM")],
               "VSYS",
               "ESC_TELEM", "NRST", "SWCLK", "SWDIO", "SWO", "SAFETY_BTN"]

# Top-layer areas other nets must stay out of once the PRE_ROUTE nets are in (x1, y1, x2, y2).
GUARDS = [(-13.9, -3.9, -10.0, 3.3)]        # crystal and its load capacitors


def rect(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# The battery corner. All battery current enters and leaves the back-left lobe through the
# 11 x 11 mm square where the lobe meets the centre of the board, on the VBAT plane (plus)
# and the GND plane (minus). Every via there is a hole in three of the four planes, so that
# square is kept free of vias and of parts that need them (gen/power_check.py measures it).
NO_VIA_AREAS = [(-27.6, 17.4, -17.4, 27.6)]

# Copper pours on the outer layers for the high-current paths.
POURS = [
    # battery + pad to the shunt; wraps the top and left of the shunt pad (this is 1 oz copper)
    # the same shape again on the bottom layer and as an island in the (2 oz) VBAT plane layer
    *[dict(net="VBAT_IN", layer=layer, poly=[(-42.9, 18.2), (-38.3, 18.2), (-38.3, 23.5), (-39.1, 23.5),
                                             (-39.1, 26.4), (-42.9, 26.4)]) for layer in ("F", "B", "In3.Cu")],
    # shunt to the via field, which sits right where the lobe meets the centre of the board
    dict(net="VBAT", layer="F", poly=[(-35.1, 22.75), (-33.45, 22.75), (-33.45, 23.6), (-28.35, 23.6),
                                      (-28.35, 28.9), (-33.2, 28.9), (-33.2, 26.4), (-35.1, 26.4)]),
    dict(net="VBAT", layer="B", poly=[(-35.1, 22.75), (-33.45, 22.75), (-33.45, 23.6), (-28.35, 23.6),
                                      (-28.35, 28.9), (-35.1, 28.9)]),
    dict(net="5V", layer="F", poly=rect(-20.45, 27.75, -17.35, 36.05)),        # buck output
]

# Extra vias: (net, x, y, diameter, drill).
STITCH_VIAS = (
    # battery + pad to the shunt: ties the three VBAT_IN layers together next to the shunt pad
    [("VBAT_IN", x, y, *PWR_VIA) for x in (-41.2, -42.2) for y in (24.0, 24.95, 25.9)]
    + [("VBAT_IN", x, 23.2, *PWR_VIA) for x in (-40.6, -39.6)]
    # shunt to the VBAT plane: large vias against the shunt pad, then a field of smaller ones
    + [("VBAT", -32.5, y, *BIG_VIA) for y in (24.3, 25.7, 27.1)]
    + [("VBAT", x, 23.2, *PWR_VIA) for x in (-34.6,)]
    + [("VBAT", x, y, *PWR_VIA) for x in (-31.15, -30.15, -29.15)
       for y in (24.05, 25.05, 26.05, 27.05, 28.05)]
    # 5 V buck output into the 5V plane, either side of the inductor pad
    + [("5V", x, y, VIA_DIA, VIA_DRILL) for x in (-19.6, -17.75) for y in (28.1, 35.6)]
    # thermal vias under the LMR33630 exposed pad (U5 at -31.0, 32.15)
    + [("GND", -31.0 + dx, 32.15 + dy, VIA_DIA, VIA_DRILL) for dx in (-0.6, 0.6) for dy in (-0.775, 0.775)]
)

# ---------------------------------------------------------------------------
# Footprint shorthands
# ---------------------------------------------------------------------------
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
R0402 = "Resistor_SMD:R_0402_1005Metric"
GH4 = "Connector_JST:JST_GH_BM04B-GHS-TBT_1x04-1MP_P1.25mm_Vertical"
GH6 = "Connector_JST:JST_GH_BM06B-GHS-TBT_1x06-1MP_P1.25mm_Vertical"
TP = "TestPoint:TestPoint_Pad_D1.5mm"

PARTS = []
SECTIONS = []          # schematic sheets, in order: (key, title)
_section = [None]


def section(key, title=None):
    """Parts defined after this call belong to schematic sheet `key`."""
    if title and key not in [k for k, _t in SECTIONS]:
        SECTIONS.append((key, title))
    _section[0] = key


def part(ref, fp, value, x, y, rot=0, side="F", nets=None, note="", bom=True):
    PARTS.append(dict(ref=ref, fp=fp, value=value, x=x, y=y, rot=rot, side=side,
                      nets=nets or {}, note=note, section=_section[0], bom=bom))


def cap(ref, value, x, y, a, b="GND", rot=0, side="F", fp=C0402):
    part(ref, fp, value, x, y, rot, side, {"1": a, "2": b})


def res(ref, value, x, y, a, b, rot=0, side="F"):
    part(ref, R0402, value, x, y, rot, side, {"1": a, "2": b})


# ---------------------------------------------------------------------------
# MCU — nets by pin NAME; pin numbers are resolved from KiCad's symbol library
# ---------------------------------------------------------------------------
section("mcu", "MCU, clock, debug, status")
MCU_NETS = {
    # port outputs: one timer per role (S1 = TIM1, S2 = TIM4, S3 = TIM3)
    "PE9": "P0_S1", "PE11": "P1_S1", "PE13": "P2_S1", "PE14": "P3_S1",
    "PD12": "P0_S2", "PD13": "P1_S2", "PD14": "P2_S2", "PD15": "P3_S2",
    "PC6": "P0_S3", "PC7": "P1_S3", "PB0": "P2_S3", "PB1": "P3_S3",
    "PB5": "P0_ID", "PA10": "P1_ID", "PB2": "P2_ID", "PC1": "P3_ID",
    "PD3": "LATCH0", "PD4": "LATCH1", "PD7": "LATCH2", "PD10": "LATCH3",
    # port 5 V switches: enable (high = on) and fault (low = overcurrent), each on the MCU
    # edge that faces its port
    "PE1": "P0_EN", "PB12": "P1_EN", "PE12": "P2_EN", "PA2": "P3_EN",
    "PB4": "P0_FLT", "PD11": "P1_FLT", "PE10": "P2_FLT", "PA1": "P3_FLT",
    "PE0": "ESC_TELEM",
    # IMU on SPI4: these five pins are the MCU corner next to the sensor
    "PE2": "IMU_SCK", "PE5": "IMU_MISO", "PE6": "IMU_MOSI", "PE3": "IMU_CS", "PE4": "IMU_DRDY",
    "PB10": "I2C2_SCL", "PB11": "I2C2_SDA",
    # microSD
    "PC8": "SD_D0", "PC9": "SD_D1", "PC10": "SD_D2", "PC11": "SD_D3", "PC12": "SD_CK",
    "PD2": "SD_CMD", "PA8": "SD_DET",
    # connectors
    "PB6": "GPS_TX", "PB7": "GPS_RX", "PB8": "I2C1_SCL", "PB9": "I2C1_SDA",
    "PD5": "TELEM1_TX", "PD6": "TELEM1_RX", "PD8": "RC_TX", "PD9": "RC_RX",
    "PE8": "DBG_TX", "PE7": "DBG_RX",
    "PA11": "USB_D_N", "PA12": "USB_D_P", "PA9": "USB_VBUS_SENSE",
    "PA13": "SWDIO", "PA14": "SWCLK", "PB3": "SWO", "NRST": "NRST",
    # housekeeping
    "PC0": "V5_SENSE", "PA0": "BUZZER", "PC13": "LED_R", "PC14": "LED_G", "PC15": "LED_B",
    "PA15": "SAFETY_BTN", "BOOT0": "BOOT0", "PH0": "OSC_IN", "PH1": "OSC_OUT",
    # power
    "VDD": "3V3", "VSS": "GND", "VDDA": "3V3A", "VREF+": "3V3A", "VSSA": "GND", "VBAT": "3V3",
}
MCU_VCAP = {"48": "VCAP1", "73": "VCAP2"}

# The peripheral function each signal relies on; checked against the alternate-function
# list in KiCad's STM32H743VITx symbol by make_schematic.py.
MCU_FUNCS = {
    "PE9": "TIM1_CH1", "PE11": "TIM1_CH2", "PE13": "TIM1_CH3", "PE14": "TIM1_CH4",
    "PD12": "TIM4_CH1", "PD13": "TIM4_CH2", "PD14": "TIM4_CH3", "PD15": "TIM4_CH4",
    "PC6": "TIM3_CH1", "PC7": "TIM3_CH2", "PB0": "TIM3_CH3", "PB1": "TIM3_CH4",
    "PE0": "UART8_RX",
    "PE2": "SPI4_SCK", "PE5": "SPI4_MISO", "PE6": "SPI4_MOSI",
    "PB10": "I2C2_SCL", "PB11": "I2C2_SDA", "PB8": "I2C1_SCL", "PB9": "I2C1_SDA",
    "PC8": "SDMMC1_D0", "PC9": "SDMMC1_D1", "PC10": "SDMMC1_D2", "PC11": "SDMMC1_D3",
    "PC12": "SDMMC1_CK", "PD2": "SDMMC1_CMD",
    "PB6": "USART1_TX", "PB7": "USART1_RX", "PD5": "USART2_TX", "PD6": "USART2_RX",
    "PD8": "USART3_TX", "PD9": "USART3_RX", "PE8": "UART7_TX", "PE7": "UART7_RX",
    "PA11": "USB_OTG_FS_DM", "PA12": "USB_OTG_FS_DP", "PA9": "USB_OTG_FS_VBUS",
    "PA13": "DEBUG_JTMS-SWDIO", "PA14": "DEBUG_JTCK-SWCLK", "PB3": "DEBUG_JTDO-SWO",
    "PC0": "ADC1_INP10", "PA0": "TIM2_CH1", "PH0": "RCC_OSC_IN", "PH1": "RCC_OSC_OUT",
}

part("U1", "Package_QFP:LQFP-100_14x14mm_P0.5mm", "STM32H743VIT6", 0, 0, nets="MCU")

# MCU support, bottom side directly under the pins they serve
cap("C1", "100n", -5.2, -1.25, "3V3", rot=90, side="B")      # VDD 11 / VSS 10
cap("C2", "100n", -5.75, 5.2, "3V3", side="B")               # VDD 27 / VSS 26
cap("C3", "100n", 5.75, 5.2, "3V3", side="B")                # VDD 50 / VSS 49
cap("C4", "100n", 5.2, -5.75, "3V3", rot=90, side="B")       # VDD 75 / VSS 74
cap("C5", "100n", -5.75, -5.2, "3V3", side="B")              # VDD 100 / VSS 99
cap("C6", "2u2", 3.9, 3.6, "VCAP1", side="B", fp=C0603)      # VCAP 48
cap("C7", "2u2", 3.4, -3.4, "VCAP2", side="B", fp=C0603)     # VCAP 73
cap("C8", "100n", -5.2, 3.5, "3V3A", rot=90, side="B")       # VDDA 21 / VSSA 19
cap("C9", "1u", -3.9, 3.5, "3V3A", rot=90, side="B")
part("FB1", "Inductor_SMD:L_0603_1608Metric", "600R@100MHz", -2.4, 3.5, 90, "B",
     {"1": "3V3", "2": "3V3A"})
cap("C10", "4u7", 0.0, 0.0, "3V3", side="B", fp=C0603)

part("Y1", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", "16MHz CL 8pF", -11.9, -0.25, 90,
     nets={"1": "OSC_OUT", "3": "OSC_IN", "2": "GND", "4": "GND"},
     note="Load capacitance 8 pF (10 pF capacitors + about 3 pF stray), ESR 80 ohm or less.")
cap("C11", "10p", -11.9, -3.1, "OSC_IN")
cap("C12", "10p", -11.9, 2.6, "OSC_OUT")
cap("C13", "100n", -11.9, 4.7, "NRST")
res("R1", "10k", -3.0, -11.0, "BOOT0", "GND", rot=90)
part("TP1", TP, "BOOT0", -3.0, -13.6, nets={"1": "BOOT0"}, bom=False)
res("R2", "10k", -14.5, 6.0, "VSYS", "V5_SENSE")
cap("C32", "100n", -16.7, 7.4, "V5_SENSE")                   # holds the ADC sample
res("R24", "10k", -5.2, -11.0, "3V3", "ESC_TELEM", rot=90)   # UART8 RX idles high with no ESC
res("R3", "10k", -14.5, 7.4, "V5_SENSE", "GND")
part("TP2", TP, "DBG_TX", 1.5, 12.5, nets={"1": "DBG_TX"}, bom=False)
part("TP3", TP, "DBG_RX", -2.0, 12.5, nets={"1": "DBG_RX"}, bom=False)
part("TP4", TP, "BUZZER", -15.5, 11.5, nets={"1": "BUZZER"}, bom=False)

# ---------------------------------------------------------------------------
# Sensors (own quiet 3V3S rail)
# ---------------------------------------------------------------------------
section("sensors", "Sensors and storage")
# ICM-42688-P pin-out from TDK DS-000347 rev 1.2, table 9 / figure 4:
#   1 AP_SDO  4 INT1  5 VDDIO  6 GND  7 RESV (must be GND)  8 VDD
#   9 INT2/FSYNC/CLKIN (GND when unused)  12 AP_CS  13 AP_SCLK  14 AP_SDI
#   2, 3, 10, 11 RESV (no connect or GND)
# Placed against the MCU corner that carries SPI4, so the bus is a few millimetres long.
part("U2", "Package_LGA:LGA-14_3x2.5mm_P0.5mm_LayoutBorder3x4y", "ICM-42688-P", -12.8, -7.4, 270,
     nets={"1": "IMU_MISO", "4": "IMU_DRDY", "5": "3V3S", "6": "GND", "7": "GND", "8": "3V3S",
           "9": "GND", "12": "IMU_CS", "13": "IMU_SCK", "14": "IMU_MOSI"},
     note="Pin-out per TDK DS-000347 table 9. Pins 2, 3, 10, 11 are reserved: left open.")
cap("C14", "100n", -13.07, -4.8, "3V3S")                     # VDD, pin 8
cap("C29", "2u2", -15.2, -4.8, "3V3S", rot=180)              # VDD bulk (datasheet: 2.2 uF)
cap("C15", "10n", -15.1, -7.6, "3V3S", rot=270)              # VDDIO, pin 5 (datasheet: 10 nF)
# DPS310 pin-out (Infineon): 1 GND, 2 CSB, 3 SDI/SDA, 4 SCK/SCL, 5 SDO, 6 VDDIO, 7 GND, 8 VDD.
# CSB high selects I2C; SDO low selects address 0x76.
part("U3", "Package_LGA:Bosch_LGA-8_2x2.5mm_P0.65mm_ClockwisePinNumbering", "DPS368", -25.5, -28.0,
     nets={"1": "GND", "2": "3V3S", "3": "I2C2_SDA", "4": "I2C2_SCL", "5": "GND",
           "6": "3V3S", "7": "GND", "8": "3V3S"},
     note="DPS310 is discontinued; DPS368 is the pin- and register-compatible successor. "
          "I2C address 0x76. Check the land pattern against the Infineon drawing.")
cap("C16", "100n", -25.5, -30.3, "3V3S")
res("R4", "2k2", -28.6, -27.5, "3V3", "I2C2_SDA")
res("R5", "2k2", -28.6, -28.9, "3V3", "I2C2_SCL")
part("U7", "Package_TO_SOT_SMD:SOT-23-5", "LP5907MFX-3.3", -21.0, -20.6,
     nets={"1": "VSYS", "2": "GND", "3": "VSYS", "5": "3V3S"})
cap("C17", "2u2", -21.0, -23.6, "VSYS")                      # > 0.7 uF effective after DC bias
cap("C18", "2u2", -24.6, -20.6, "3V3S", rot=90)
# 3V3P: the 3.3 V that goes out to the port contacts has its own current-limited regulator,
# so a shorted module or a contact touching during insertion cannot pull down the MCU's 3V3.
part("U17", "Package_TO_SOT_SMD:SOT-23-5", "LP5907MFX-3.3", -20.6, -27.2,
     nets={"1": "VSYS", "2": "GND", "3": "VSYS", "5": "3V3P"},
     note="Port 3.3 V: 250 mA, current-limited. Separate from the MCU and sensor rails.")
cap("C44", "2u2", -20.6, -30.2, "VSYS")
cap("C45", "2u2", -17.9, -27.2, "3V3P", rot=90)

# ---------------------------------------------------------------------------
# Battery input, current sense, 5 V buck (back-left lobe)
# ---------------------------------------------------------------------------
section("power", "Battery input and regulators")
WIRE = "Connector_Wire:SolderWire-2.5sqmm_1x01_D2.4mm_OD3.6mm"
part("J9", WIRE, "BAT+", -40.6, 20.5, nets={"1": "VBAT_IN"}, bom=False,
     note="Solder pad for the battery lead. 3.0 mm hole: takes 12-14 AWG.")
# BAT- sits against the neck of the lobe so the return current goes straight into the board.
part("J10", WIRE, "BAT-", -31.2, 20.5, nets={"1": "GND"}, bom=False)
# 2512 shunt on a four-pad footprint: pads 1 and 4 carry the current, pads 2 and 3 are
# separate sense pads so the INA226 does not measure the copper drop.
part("R6", "fera:R_2512_Kelvin", "0R0002 2512", -37.0, 25.6,
     nets={"1": "VBAT_IN", "2": "ISNS_P", "3": "ISNS_N", "4": "VBAT"},
     note="0.2 mOhm metal-strip shunt, 4 W or more: 0.7 W at 60 A, 2.9 W at 120 A. "
          "PX4: INA226_SHUNT = 0.0002.")
part("U4", "Package_SO:MSOP-10_3x3mm_P0.5mm", "INA226", -38.1, 30.0, 180,
     nets={"1": "GND", "2": "GND", "4": "I2C2_SDA", "5": "I2C2_SCL", "6": "3V3", "7": "GND",
           "8": "VBAT", "9": "ISNS_N", "10": "ISNS_P"},
     note="A0 = A1 = GND: I2C address 0x40 (start the PX4 ina226 driver with -a 0x40).")
cap("C19", "100n", -42.2, 29.4, "3V3", rot=90)
part("C20", "Capacitor_SMD:CP_Elec_6.3x7.7", "220u 35V", -28.9, 36.7, 90, "B",
     {"1": "VBAT", "2": "GND"})
part("D5", "Diode_SMD:D_SMB", "SMBJ18A", -38.6, 30.0, 0, "B", {"1": "VBAT", "2": "GND"},
     note="Clamps connector and ESC spikes on a 4S pack (16.8 V full). Pad 1 = cathode.")
# 5 V buck: 100 nF directly under VIN/PGND, bulk input capacitor beside it, inductor against
# SW, output capacitors under the inductor on the bottom side.
part("U5", "Package_SO:HSOP-8-1EP_3.9x4.9mm_P1.27mm_EP2.41x3.1mm", "LMR33630ADDA", -31.0, 32.15,
     nets={"1": "GND", "2": "VBAT", "3": "VBAT", "5": "BUCK_FB", "6": "BUCK_VCC",
           "7": "BUCK_BOOT", "8": "BUCK_SW", "9": "GND"})
cap("C21", "10u 50V", -33.5, 37.7, "VBAT", fp=C1206)
cap("C30", "10u 50V", -33.65, 30.85, "VBAT", rot=90, side="B", fp=C0805)   # directly under VIN/PGND
part("L1", "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm", "10u 5A", -21.6, 32.0,
     nets={"1": "BUCK_SW", "2": "5V"},
     note="Saturation current must be at least 5.1 A (LMR33630 high-side limit); confirm the part.")
cap("C22", "22u 16V", -19.6, 30.0, "5V", side="B", fp=C1210)
cap("C23", "22u 16V", -19.6, 33.4, "5V", side="B", fp=C1210)
cap("C34", "22u 16V", -24.5, 30.0, "5V", side="B", fp=C1210)
cap("C24", "100n", -26.675, 31.0, "BUCK_BOOT", "BUCK_SW", rot=90)
cap("C25", "1u", -26.675, 33.25, "BUCK_VCC", rot=270)
res("R7", "100k", -30.9, 35.95, "5V", "BUCK_FB")
res("R8", "24k9", -28.7, 35.95, "BUCK_FB", "GND")

# 3V3 buck (back-right lobe)
part("U6", "Package_TO_SOT_SMD:SOT-23-5", "TLV62569DBV", 32.0, 36.2,
     nets={"1": "VSYS", "2": "GND", "3": "V3_SW", "4": "VSYS", "5": "V3_FB"})
part("L2", "Inductor_SMD:L_Coilcraft_XAL4020-XXX", "2u2 Isat>3A", 27.5, 35.8,
     nets={"1": "V3_SW", "2": "3V3"}, note="XAL4020-222 class: saturation above the 3 A switch limit.")
cap("C26", "10u", 32.0, 36.2, "VSYS", side="B", fp=C0805)
cap("C35", "6p8", 30.4, 38.6, "3V3", "V3_FB", side="B")       # feed-forward, per the TLV62569 datasheet
# Bulk capacitance and a clamp on the 5 V port rail: servos feed energy back into it.
part("C31", "Capacitor_SMD:CP_Elec_6.3x7.7", "220u 10V", 38.5, 24.8, 0, "B", {"1": "5V", "2": "GND"})
part("D7", "Diode_SMD:D_SMA", "SMAJ5.0A", 38.0, 31.3, 0, "B", {"1": "5V", "2": "GND"},
     note="Clamps the 5 V port rail. Pad 1 = cathode.")
cap("C27", "22u", 27.0, 39.3, "3V3", fp=C0805)
res("R9", "453k", 28.0, 37.6, "3V3", "V3_FB", side="B")
res("R10", "100k", 28.0, 39.1, "V3_FB", "GND", side="B")

# microSD (back-right lobe)
section("sensors", None)
part("J11", "Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5", "microSD", 26.2, 25.2, 90,
     nets={"1": "SD_D2", "2": "SD_D3", "3": "SD_CMD", "4": "3V3", "5": "SD_CK", "6": "GND",
           "7": "SD_D0", "8": "SD_D1", "9": "GND", "10": "SD_DET", "11": "GND"})
cap("C28", "100n", 15.8, 22.0, "3V3", rot=90)
cap("C46", "4u7", 14.2, 22.0, "3V3", rot=90, fp=C0603)        # bulk at the card socket

# ---------------------------------------------------------------------------
# USB-C on the tongue, SWD, UI (front-right lobe)
# ---------------------------------------------------------------------------
section("io", "USB, debug and external connectors")
part("J12", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", "USB-C",
     53.6, -22.75, 90,
     nets={"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "S1": "GND",
           "A4": "USB_VBUS", "A9": "USB_VBUS", "B4": "USB_VBUS", "B9": "USB_VBUS",
           "A5": "USB_CC1", "B5": "USB_CC2",
           "A6": "USB_CONN_D_P", "B6": "USB_CONN_D_P", "A7": "USB_CONN_D_N", "B7": "USB_CONN_D_N"})
res("R11", "5k1", 47.3, -18.2, "USB_CC1", "GND")
res("R12", "5k1", 47.3, -27.6, "USB_CC2", "GND")
part("U8", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-2SC6", 44.4, -22.75, 180,
     nets={"1": "USB_CONN_D_N", "6": "USB_D_N", "3": "USB_CONN_D_P", "4": "USB_D_P",
           "2": "GND", "5": "USB_VBUS"},
     note="D- enters on pin 1 and leaves on pin 6; D+ enters on 3 and leaves on 4.")
# VSYS is the system rail: the 5 V buck through D6 or USB through D1, whichever is higher.
# It feeds the 3.3 V buck, the sensor LDO and the GPS / TELEM / RC connectors. USB can no
# longer reach the 5 V port rail, so it cannot back-feed the buck, the battery or the servos.
part("D1", "Diode_SMD:D_SOD-123", "1 A Schottky", 39.5, -27.4, 0,
     nets={"1": "VSYS", "2": "USB_VBUS"}, note="USB into the system rail. Pad 1 = cathode.")
part("D6", "Diode_SMD:D_SMA", "SS34", 32.6, -29.47, 0, nets={"1": "VSYS", "2": "5V"},
     note="5 V buck into the system rail. Pad 1 = cathode.")
res("R13", "10k", 34.6, -27.1, "USB_VBUS", "USB_VBUS_SENSE")
res("R23", "10k", 34.6, -25.6, "USB_VBUS", "GND")             # VBUS reads low when unplugged
cap("C33", "1u 25V", 44.2, -26.0, "USB_VBUS", fp=C0603)
part("J13", "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical", "SWD", 26.0, -33.5,
     nets={"1": "3V3", "2": "SWDIO", "3": "NRST", "4": "SWCLK", "5": "GND", "6": "SWO"},
     bom=False, note="Bare footprint for a Tag-Connect TC2030-NL cable; nothing is fitted.")
section("mcu", None)
part("SW1", "Button_Switch_SMD:SW_SPST_B3U-1000P", "SAFETY", 35.5, -33.0,
     nets={"1": "SAFETY_BTN", "2": "GND"})
for i, (name, x) in enumerate((("R", 26.0), ("G", 28.5), ("B", 31.0))):
    part(f"D{i + 2}", "LED_SMD:LED_0603_1608Metric", f"LED {name}", x, -40.5, 90,
         nets={"1": f"LED_{name}", "2": f"LED_{name}_A"}, note="Pad 1 = cathode, sunk by the MCU.")
    # PC13-15 may sink about 3 mA; green and blue need less resistance than red to be visible
    res(f"R{14 + i}", "680R" if name == "R" else "330R", x, -37.3, "3V3", f"LED_{name}_A", rot=90)
section("io", None)
part("J14", GH6, "LATCH", 36.0, -21.0,
     nets={"1": "LATCH0", "2": "LATCH1", "3": "LATCH2", "4": "LATCH3", "5": "3V3", "6": "GND",
           "MP": "GND"})

# ---------------------------------------------------------------------------
# GPS / telemetry / RC connectors (front-left lobe)
# ---------------------------------------------------------------------------
part("J15", GH6, "GPS", -36.5, -21.0,
     nets={"1": "VSYS", "2": "GPS_TX", "3": "GPS_RX", "4": "I2C1_SCL", "5": "I2C1_SDA", "6": "GND",
           "MP": "GND"})
part("J16", GH6, "TELEM1", -36.5, -28.5,
     nets={"1": "VSYS", "2": "TELEM1_TX", "3": "TELEM1_RX", "6": "GND", "MP": "GND"})
part("J17", GH4, "RC", -30.0, -36.5,
     nets={"1": "VSYS", "2": "RC_TX", "3": "RC_RX", "4": "GND", "MP": "GND"})
res("R17", "2k2", -27.5, -19.0, "3V3", "I2C1_SCL")
res("R18", "2k2", -27.5, -20.4, "3V3", "I2C1_SDA")

# ---------------------------------------------------------------------------
# The four FERA ports. Laid out once for FRONT, then rotated.
# ---------------------------------------------------------------------------
section("ports", "FERA ports")
PORT_ANGLE = {0: 0, 1: 270, 2: 180, 3: 90}      # FRONT, RIGHT, BACK, LEFT
PORT_NAME = {0: "FRONT", 1: "RIGHT", 2: "BACK", 3: "LEFT"}


def rotate(x, y, deg):
    """KiCad's on-screen rotation (positive = counter-clockwise, Y down)."""
    a = math.radians(deg)
    c, s = round(math.cos(a), 9), round(math.sin(a), 9)
    return (x * c + y * s, -x * s + y * c)


for p in range(4):
    a = PORT_ANGLE[p]
    x, y = rotate(-6.6, -21.5, a)
    # Polarity per the Amass XT30PW-F drawing: the "+" contact is the one at the flat end of
    # the housing, which is pad 2 of KiCad's footprint. Pad 1 (square pad) is "-".
    part(f"J{p + 1}", "Connector_AMASS:AMASS_XT30PW-F_1x02_P2.50mm_Horizontal",
         f"PWR {PORT_NAME[p]}", x, y, a, nets={"1": "GND", "2": "VBAT"},
         note="XT30PW-F: 15 A continuous, 30 A momentary, 0.8 mOhm (Amass spec V1.2). "
              "Pad 1 = minus, pad 2 = plus. Placeholder until the Phase 1 connector tests.")
    x, y = rotate(4.3, -25.23, a)
    part(f"J{p + 5}", "Connector_PinHeader_1.27mm:PinHeader_2x04_P1.27mm_Horizontal",
         f"SIG {PORT_NAME[p]}", x, y, a + 90,
         nets={"1": f"P{p}_S1_C", "3": f"P{p}_S2_C", "5": f"P{p}_S3_C", "7": f"P{p}_ID_C",
               "2": "3V3P", "4": "GND", "6": f"P{p}_TELEM_C", "8": f"P{p}_5V"},
         note="Placeholder for the 8-way pogo block. Pin order here is chosen for routing, "
              "not the logical order in docs/port-spec.md.")
    x, y = rotate(6.2, -19.5, a)
    res(f"R{19 + p}", "2k2", x, y, "3V3", f"P{p}_ID", rot=a)
    # --- port protection -------------------------------------------------------------
    # 5 V to the module through its own current-limited switch (TI SLVSAU6: 1.5 A rated,
    # limit 1.7 to 2.5 A, enable active high, FLT open drain and low on overcurrent or
    # overtemperature). Off until the firmware has read the module's ID.
    x, y = rotate(13.5, -25.9, a)
    part(f"U{9 + p}", "Package_TO_SOT_SMD:SOT-23-5", "TPS2069CDBV", x, y, a,
         nets={"1": f"P{p}_5V", "2": "GND", "3": f"P{p}_FLT", "4": f"P{p}_EN", "5": "5V"},
         note="Pin-out per TI SLVSAU6 table 5-2: 1 OUT, 2 GND, 3 FLT, 4 EN, 5 IN.")
    x, y = rotate(10.4, -25.9, a)
    cap(f"C{36 + p}", "10u 16V", x, y, f"P{p}_5V", rot=a + 90, fp=C0805)
    x, y = rotate(13.5, -25.9, a)
    cap(f"C{40 + p}", "100n", x, y, "5V", rot=a + 90, side="B")   # under the switch's IN pin
    x, y = rotate(15.3, -23.3, a)
    res(f"R{29 + p}", "10k", x, y, f"P{p}_EN", "GND", rot=a)     # off while the MCU is in reset
    # 100 ohm in series with S1, S2, S3 and ID, 1 k in the telemetry line (which joins the
    # other ports behind it), and a diode array to 3V3 and GND on the contact side.
    x, y = rotate(6.2, -22.95, a)
    part(f"RN{p + 1}", "Resistor_SMD:R_Array_Convex_4x0402", "100R x4", x, y, a + 90,
         nets={"8": f"P{p}_S1_C", "7": f"P{p}_S2_C", "6": f"P{p}_S3_C", "5": f"P{p}_ID_C",
               "1": f"P{p}_S1", "2": f"P{p}_S2", "3": f"P{p}_S3", "4": f"P{p}_ID"})
    x, y = rotate(10.2, -23.3, a)
    res(f"R{25 + p}", "1k", x, y, f"P{p}_TELEM_C", "ESC_TELEM", rot=a)
    x, y = rotate(6.2, -21.9, a)
    part(f"U{13 + p}", "Package_TO_SOT_SMD:SOT-23-6", "USBLC6-4SC6", x, y, a, "B",
         nets={"1": f"P{p}_S1_C", "3": f"P{p}_S2_C", "4": f"P{p}_S3_C", "6": f"P{p}_ID_C",
               "2": "GND", "5": "3V3"},
         note="Clamps the contact side of S1-S3 and ID to 3V3 and GND. Its supply pin is on 3V3, "
              "not on the port's 5 V, so signals cannot back-power a switched-off module rail.")

section("io")
for i, (x, y) in enumerate(MOUNT_HOLES):
    part(f"H{i + 1}", "MountingHole:MountingHole_3.2mm_M3_Pad", "M3", x, y, bom=False)

# Not on this board (see pinmap.md): second IMU, FRAM, CAN, ESC-telemetry mux,
# buzzer driver, RGB LED driver, reverse-polarity protection.
