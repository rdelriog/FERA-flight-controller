# Legacy hardware (reference only)

| Folder | What | Why it is not carried forward |
|---|---|---|
| `mark1-kicad/` | KiCad 8 "Mark I" main board: STM32F730R8, MPU-9250, BMP280, 4x JST-XH arm ports. `GND_VLIPO_Plane.kicad_pcb` is the newest layout. | 64 KB flash cannot run PX4; VDD pins tied to the VBAT net, VCAP/NRST/SWD unconnected, no crystal, no USB-C CC resistors, no SD card, no battery sensing; arm port has one signal and 3 A pins. |
| `altium-2021/` | Altium dev board from 2021: STM32F103, MPU-6050, BMP280, microSD. | Altium format, obsolete parts. |
| `cubemx-nucleo-f722/` | STM32CubeMX project for a Nucleo-F722ZE (template only, empty main loop). | PX4 replaces the HAL-based firmware. |
| `mechanical/` | Hub baseplate DXF/DWG from the first prototype. | Re-authored parametrically in `cad/`. |
