#include "imu.h"
void imu_init(void){}
imu_sample_t imu_latest(void){ static imu_sample_t s={0}; return s; }
