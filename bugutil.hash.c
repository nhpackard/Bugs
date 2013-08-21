#include "bugs.h"


#define MAXTRY 2*NMAX

Bug* randombug(int alive)
{
    int i,done;
    b = (Bug *) calloc(1,sizeof (Bug));
    b -> food = 255;
    b -> x = n_rand(ROWL);
    b -> y = n_rand(NROWS);
    
    for(i=0;i<NMOVE;i++){
        b->movex[i] = n_rand(MAXMV);
        b->movey[i] = n_rand(MAXMV);
    }
    b->mutrate = mutrate;          // initialize to global for now...

    if(alive){
        for(i=0,done=0; i<MAXTRY; i++){
            if(nodes[NODE(b->x,b->y)].bug ==0){
                nodes[NODE(b->x,b->y)].bug = b;
                done=1;
                break;
            }
            else{
                b -> x = n_rand(ROWL);
                b -> y = n_rand(NROWS);
            }
        }
        if(!done){
            fprintf(stderr,"Couldn't place bug after MAXTRY tries.\n");
            exit(10);
        }
        b->alive = 1;
    }
    else{
        b->alive = 0;
    }
    return b;
}
    
// initialize bugs alive and dead arrays
// make N of them alive
// with random genes.
void initbugs(int N)
{
    int i;
    khInitAlive();
    khInitDead();
    for(i=0; i<N; i++)
        khPutAlive(randombug(1));
    for(i=N; i<NMAX; i++)
        khPutDead(randombug(0));
    Nalive = N;
    Ndead = NMAX-N;
}
    
void copybug(Bug *b, Bug *bb)
{
    int i;
    bb->food = b->food;
    bb->x = bb->x;    bb->y = bb->y;
    bb->alive = bb->alive;
    for(i=0;i<NMOVE;i++){
        bb->movex[i] = b->movex[i];
        bb->movey[i] = b->movey[i];
        bb->act[i] = b->act[i];
    }
}

void killbug(Bug *b)
{
    int nn,i,done;
    nn = NODE(b->x,b->y);
    assert(nodes[nn].bug == b);
    nodes[nn].bug = 0;
    b->alive = 0;
    dead[Ndead++] = b;
    done=0;
    // painful... shouldn't use an array.
    for(i=0; i< Nalive; i++)
        if(b==alive[i]){
            for(j=i; j<Nalive-1; j++)
                alive[j] = alive[j+1];
            done=1;
        }
    assert(done==1);
}
        

void movebug(Bug *b,int dx,int dy)
{
    int cnt,nn;
    Bug * btmp;
    ADDX(b->x,dx);       // mod ROWL
    ADDY(b->x,dy);
    b->food -= dx+dy;
    if(b->food <0)
        killbug(b);
    nn = NODE(b->x,b->y);
    btmp = nodes[nn].bug;
    if(btmp != 0)
        while(jitterbug(btmp))
            ;

}
void jitterbug(Bug *b)          // jitter x,y until find an empty spot
{                               // return 1 if still jittering, 0 if success
    int dx,dy,nn;
    dx = n_rand(MAXMV);
    dy = n_rand(MAXMV);
    ADDX(b->x,dx);       // mod ROWL
    ADDY(b->x,dy);
    b->food -= dx+dy;
    if(b->food<0){
        killbug(b);
        return 0;
    }
    nn = NODE(b->x,b->y);
    if(nodes[nn].bug == 0){     // success
        nodes[nn].bug = b;
        return 0;
    }
    else                        // failure
        return 1;
}

void sensemove(Bug *b)
{
    int i,nn;
    int sense=0;
    int dx,dy;
    nn = NODE(b->x,b->y);       // which node the bug is at

    sense = nodes[nodes[nn].Nbrs[0]].food > 0 ? 1:0;
    for(i=1;i<NNBRS;i++){
        sense << 1;
        sense |= (nodes[nodes[nn].Nbrs[i]].food > 0 ? 1:0);
    }
    assert(sense < NMOVE);
    dx = b->movex[sense];
    dy = b->movey[sense];
    movebug(b,dx,dy);
}
    

void updatebugs()
{
    int i;
    for(i=0;i<Nalive; i++)
        sensemove(alive[i]);
}

