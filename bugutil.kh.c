#include "bugs.h"


    
// ------------------------ beginning of routinges that use the hash sets

// initialize bugs alive and dead arrays
// make N of them alive
// with random genes.
void initbugs(int N)
{
    int i;
    Bug * b;
    for(i=0; i<N; i++){
        b = randombug(1);        // 1 => alive, placed in nodes
        khPutAlive(b);
    }
    for(i=N; i<NMAX; i++){
        b = randombug(0);        // 0 => dead, not placed
        khPutDead(b);
    }
}
    

void splitbug(Bug *b)
{
    int tst;
    Bug * bb;
    bb = khGetDead();
    copybug(b,bb);
    b->food /= 2.0;
    bb->food /= 2.0;
    mutatebug(bb);
    tst = 0;
    while(tst == 0){
        tst = jitterbug(bb);
        if(tst==-1){
            killbug(bb);
            break;
        }
        if(tst==1){
            khPutAlive(bb);
            break;
        }
    }
    return;                     // -1 => bug died during jittering
}

void killbug(Bug *b)
{
    int nn;
    nn = NODE(b->x,b->y);
//    assert(nodes[nn].bug == b);
    nodes[nn].bug = 0;
    khDelAlive(b);
    khPutDead(b);
}

// -------------------- end of routines that use the hash sets

#define MAXTRY 2*NMAX

Bug* randombug(int alive)
{
    Bug * b;
    int i,done,nn;
    b = (Bug *) calloc(1,sizeof (Bug));
    b -> thisbug = b;
    b -> food = 1.0;
    for(i=0;i<NMOVE;i++){
        b->movex[i] = n_rand(MAXMV);
        b->movey[i] = n_rand(MAXMV);
    }
    b->mutrate = mutrate;          // initialize to global for now...

    if(alive){
        b -> x = n_rand(ROWL);
        b -> y = n_rand(NROWS);
        nn = NODE(b->x,b->y);
        for(i=0,done=0; i<MAXTRY; i++){
            if(nodes[NODE(b->x,b->y)].bug ==0){
                done=1;         // don't set nodes here; done in utPutAlive
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

void mutatebug(Bug *b)
{
    int i;
    float ftmp;
    for(i=0; i<NMOVE; i++){
        ftmp = f_rand();
        if(ftmp < mutrate)
            b->movex[i] = n_rand(MAXMV);
        ftmp = f_rand();
        if(ftmp < mutrate)
            b->movey[i] = n_rand(MAXMV);
    }
}
        

void movebug(Bug *b,int dx,int dy)
{
    int cnt,nn;
    Bug * btmp;
    b->food -= movetax*(dx+dy);
    if(b->food <0){
        killbug(b);
        return;
    }
    nn = NODE(b->x,b->y);   // current node
    nodes[nn].bug=0;
    ADDX(b,dx);       // mod ROWL
    ADDY(b,dy);
    nn = NODE(b->x,b->y);   // new node
    btmp = nodes[nn].bug;   // old bug at new node
    nodes[nn].bug = b;      // install b at new node
    if(nodes[nn].food>0)
        b->food += mouthfull;
    if(b->food >1)
        splitbug(b);                
    if(btmp != 0){
        int tst=0;
        while(tst == 0){
            tst = jitterbug(btmp);
            if(tst==-1){
                killbug(btmp);
                break;
            }
            if(tst==1){
                nn = NODE(btmp->x,btmp->y); // 
                nodes[nn].bug=btmp;         // don't use khPutAlive because btmp is already alive.
                break;
            }
        }
        cnt = 1;                // for debug
    }
}

int jitterbug(Bug *b)          // jitter x,y until find an empty spot
{                               // return 0 if still jittering, 1 if success
    int dx,dy,nn;
    dx = n_rand(MAXMV);
    dy = n_rand(MAXMV);
    b->food -= movetax*(dx+dy);
    if(b->food<0){
        return -1;
    }
    ADDX(b,dx);       // mod ROWL
    ADDY(b,dy);
    nn = NODE(b->x,b->y);
    if(nodes[nn].bug == 0){     // success
        return 1;
    }
    else                        // failure
        return 0;
}

void sensemove(Bug *b)
{
    int i,nn;
    int sense=0;
    int dx,dy;
    nn = NODE(b->x,b->y);       // which node the bug is at

    sense = nodes[nodes[nn].Nbrs[0]].food > 0 ? 1:0;
    for(i=1;i<NNBRS;i++){
        sense = sense << 1;
        sense |= (nodes[nodes[nn].Nbrs[i]].food > 0 ? 1:0);
    }
    assert(sense < NMOVE);
    dx = b->movex[sense];
    dy = b->movey[sense];
    movebug(b,dx,dy);
}
    
void checkbugs()
{
    int i,cnt;
    for(i=0,cnt=0; i<NMAX; i++)
        if(nodes[i].bug !=0)
            cnt++;
    printf("\nNalive=%d, %d on lattice.\n",Nalive,cnt);
    printf("Ndead=%d, %d blanks on lattice.\n",Ndead,NMAX-cnt);
    checkhash();
}
