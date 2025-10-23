typedef struct{float twoKp,twoKi,q0,q1,q2,q3,integralFBx,integralFBy,integralFBz;} mahony_t;
void mahony_init(mahony_t* m);
void mahony_update(mahony_t* m,float gx,float gy,float gz,float ax,float ay,float az,float dt);
