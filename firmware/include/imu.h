typedef struct { float gx,gy,gz,ax,ay,az; } imu_sample_t;
void imu_init(void);
imu_sample_t imu_latest(void);
