#include "platform.h"
#include "scheduler.h"
#include "imu.h"
#include <stdio.h>

int main(void) {
  platform_init();
  uart_dbg_init(115200);
  printf("\r\n[FC] Boot\r\n");
  imu_init();
  scheduler_init();
  while (1) {
    scheduler_wait_10ms();
    imu_sample_t s = imu_latest();
    printf("G:%.3f %.3f %.3f  A:%.3f %.3f %.3f\r\n", s.gx,s.gy,s.gz,s.ax,s.ay,s.az);
  }
}
