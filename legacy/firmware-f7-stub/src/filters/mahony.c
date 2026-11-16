#include "filters/mahony.h"
#include <math.h>
static float invSqrt(float x){ return 1.0f/sqrtf(x); }
void mahony_init(mahony_t* m){ m->twoKp=0.5f; m->twoKi=0; m->q0=1; m->q1=m->q2=m->q3=0; m->integralFBx=m->integralFBy=m->integralFBz=0; }
void mahony_update(mahony_t* m,float gx,float gy,float gz,float ax,float ay,float az,float dt){
  float q0=m->q0,q1=m->q1,q2=m->q2,q3=m->q3;
  float n=ax*ax+ay*ay+az*az; if(n<=0) return; n=invSqrt(n); ax*=n; ay*=n; az*=n;
  float vx=2*(q1*q3 - q0*q2), vy=2*(q0*q1 + q2*q3), vz=q0*q0 - q1*q1 - q2*q2 + q3*q3;
  float ex=(ay*vz - az*vy), ey=(az*vx - ax*vz), ez=(ax*vy - ay*vx);
  if(m->twoKi>0){ m->integralFBx+=m->twoKi*ex*dt; m->integralFBy+=m->twoKi*ey*dt; m->integralFBz+=m->twoKi*ez*dt; gx+=m->integralFBx; gy+=m->integralFBy; gz+=m->integralFBz; }
  gx+=m->twoKp*ex; gy+=m->twoKp*ey; gz+=m->twoKp*ez;
  gx*=0.5f*dt; gy*=0.5f*dt; gz*=0.5f*dt;
  float qa=q0,qb=q1,qc=q2; q0+=(-qb*gx - qc*gy - q3*gz); q1+=(qa*gx + qc*gz - q3*gy); q2+=(qa*gy - qb*gz + q3*gx); q3+=(qa*gz + qb*gy - qc*gx);
  float r=invSqrt(q0*q0+q1*q1+q2*q2+q3*q3); m->q0=q0*r; m->q1=q1*r; m->q2=q2*r; m->q3=q3*r;
}
