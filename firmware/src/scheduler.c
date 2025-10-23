#include <stdint.h>
#include "scheduler.h"
volatile uint32_t sys_ms = 0;
void scheduler_init(void) { /* init SysTick @1kHz in HAL or elsewhere */ }
void scheduler_wait_10ms(void){ uint32_t t=sys_ms; while((sys_ms - t) < 10){ __asm volatile("nop"); } }
