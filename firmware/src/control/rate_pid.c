#include "control/rate_pid.h"
void pid_init_defaults(void){}
float pid_step(pid_t* p,float sp,float meas,float dt){ float e=sp-meas; p->i+=p->ki*e*dt; float d=(e-p->prev)/dt; float u=p->kp*e + p->i + p->kd*d; if(u>p->out_max)u=p->out_max; if(u<p->out_min)u=p->out_min; p->prev=e; return u; }
