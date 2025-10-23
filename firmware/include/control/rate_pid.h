typedef struct{float kp,ki,kd,i,prev,out_min,out_max;} pid_t;
void pid_init_defaults(void);
float pid_step(pid_t* p,float sp,float meas,float dt);
