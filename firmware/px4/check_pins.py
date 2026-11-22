"""Check the PX4 board files against the FERA Core design.

    python firmware/px4/check_pins.py

Reads the MCU pin assignments from hardware/fera-core/gen/design.py (what the board is
routed with) and checks that every pin the PX4 board port uses for a function is the pin
the design gives that function, so the firmware and the PCB cannot drift apart.
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = Path(__file__).resolve().parent / "boards" / "fera" / "core-v1"

spec = importlib.util.spec_from_file_location("design", ROOT / "hardware/fera-core/gen/design.py")
design = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design)
NET = {pin: net for pin, net in design.MCU_NETS.items() if re.fullmatch(r"P[A-H]\d+", pin)}

failures = []


def expect(pin, net, where):
    got = NET.get(pin)
    ok = got == net
    print(f"  [{'ok' if ok else 'FAIL'}] {pin:5s} {net:16s} {where}" + ("" if ok else f"  (design has {got})"))
    if not ok:
        failures.append((pin, net, where))


def text(rel):
    return (BOARD / rel).read_text(encoding="utf-8")


# --- board_config.h: named GPIOs --------------------------------------------------------
cfg = text("src/board_config.h")
GPIO_RE = re.compile(r"#define\s+(GPIO_\w+)\s+/\*\s*(P[A-H]\d+)\s*\*/\s*\((.*?)\)\s*$", re.M)
ROLE = {
    "LED_RED": "LED_R", "LED_GREEN": "LED_G", "LED_BLUE": "LED_B",
    "nBTN_SAFETY": "SAFETY_BTN", "BUZZER_1": "BUZZER", "OTGFS_VBUS": "USB_VBUS_SENSE",
    "SDMMC1_NCD": "SD_DET",
}
print("board_config.h")
for name, pin, body in GPIO_RE.findall(cfg):
    port, num = re.search(r"GPIO_PORT([A-H])", body).group(1), re.search(r"GPIO_PIN(\d+)", body).group(1)
    if f"P{port}{num}" != pin:
        failures.append((pin, name, "comment and definition disagree"))
        print(f"  [FAIL] {name}: comment says {pin}, definition is P{port}{num}")
        continue
    short = name[len("GPIO_"):]
    m = re.fullmatch(r"FERA_P(\d)_(EN|nFLT|nLATCH|ID)", short)
    if m:
        p, kind = m.groups()
        net = {"EN": f"P{p}_EN", "nFLT": f"P{p}_FLT", "nLATCH": f"LATCH{p}", "ID": f"P{p}_ID"}[kind]
    elif short in ROLE:
        net = ROLE[short]
    else:
        continue
    expect(pin, net, name)
for pin, net in (("PC0", "V5_SENSE"),):
    expect(pin, net, "ADC (GPIO_ADC123_INP10)") if "GPIO_ADC123_INP10" in cfg else failures.append((pin, net, "ADC"))

# --- timer_config.cpp: PWM outputs ----------------------------------------------------------
print("timer_config.cpp")
tim = text("src/timer_config.cpp")
chans = re.findall(r"\{Timer::Timer(\d+), Timer::Channel(\d)\}, \{GPIO::Port([A-H]), GPIO::Pin(\d+)\}", tim)
role = {1: "S1", 4: "S2", 3: "S3"}
for k, (t, c, port, num) in enumerate(chans):
    t, c = int(t), int(c)
    expect(f"P{port}{num}", f"P{c - 1}_{role.get(t, '?')}", f"output {k + 1} TIM{t} CH{c}")
    want = design.MCU_FUNCS.get(f"P{port}{num}")
    if want != f"TIM{t}_CH{c}":
        failures.append((f"P{port}{num}", f"TIM{t}_CH{c}", "MCU function"))
        print(f"  [FAIL] P{port}{num}: design function {want}, board uses TIM{t}_CH{c}")
if len(chans) != 12:
    failures.append(("-", "12 outputs", f"found {len(chans)}"))

# --- spi.cpp: IMU chip select and data ready ------------------------------------------------
print("spi.cpp")
spi = text("src/spi.cpp")
for kind, net in (("CS", "IMU_CS"), ("DRDY", "IMU_DRDY")):
    port, num = re.search(rf"SPI::{kind}\{{GPIO::Port([A-H]), GPIO::Pin(\d+)\}}", spi).groups()
    expect(f"P{port}{num}", net, f"ICM-42688-P {kind}")

# --- board.h: peripheral pin selections (by comment) -----------------------------------------
print("board.h")
bh = text("nuttx-config/include/board.h")
SEL = {
    "GPIO_USART1_RX": "GPS_RX", "GPIO_USART1_TX": "GPS_TX",
    "GPIO_USART2_RX": "TELEM1_RX", "GPIO_USART2_TX": "TELEM1_TX",
    "GPIO_USART3_RX": "RC_RX", "GPIO_USART3_TX": "RC_TX",
    "GPIO_UART7_RX": "DBG_RX", "GPIO_UART7_TX": "DBG_TX", "GPIO_UART8_RX": "ESC_TELEM",
    "GPIO_SPI4_SCK": "IMU_SCK", "GPIO_SPI4_MISO": "IMU_MISO", "GPIO_SPI4_MOSI": "IMU_MOSI",
    "GPIO_I2C1_SCL": "I2C1_SCL", "GPIO_I2C1_SDA": "I2C1_SDA",
    "GPIO_I2C2_SCL": "I2C2_SCL", "GPIO_I2C2_SDA": "I2C2_SDA",
}
for name, net in SEL.items():
    m = re.search(rf"#define\s+{name}\s+.*?/\*\s*(P[A-H]\d+)", bh)
    if not m:
        failures.append(("-", net, f"{name} missing"))
        print(f"  [FAIL] {name} not found")
        continue
    expect(m.group(1), net, name)
# UART8 TX must not land on a used pin
m = re.search(r"#define\s+GPIO_UART8_TX\s+.*?/\*\s*(P[A-H]\d+)", bh)
spare = m and m.group(1) not in NET
print(f"  [{'ok' if spare else 'FAIL'}] UART8 TX parked on an unused pin ({m.group(1) if m else '?'})")
if not spare:
    failures.append(("-", "UART8 TX", "on a used pin"))
xtal = re.search(r"STM32_BOARD_XTAL\s+(\d+)ul", bh).group(1)
ok = int(xtal) == 16000000 and "16MHz" in "".join(p.get("value", "") for p in design.PARTS if p["ref"] == "Y1")
print(f"  [{'ok' if ok else 'FAIL'}] crystal {int(xtal) // 1000000} MHz matches Y1")
if not ok:
    failures.append(("PH0", "16 MHz", "crystal"))

print()
print(f"{len(failures)} problem(s)" if failures else "All board-port pins match the FERA Core design.")
sys.exit(1 if failures else 0)
