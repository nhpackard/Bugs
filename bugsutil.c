#include "bugs.h"


    
// ------------------------ beginning of routines that use the hash sets

// initialize bugs alive and dead arrays
// make N of them alive
// with random genes.
void initbugs(int N)
{
    int i;
    Bug * b;
    for(i=0; i<N; i++){
        b = randombug(1);        // 1 => alive, placed in nodes
        utPutAlive(b);
    }
    for(i=N; i<NMAX; i++){
        b = randombug(0);        // 0 => dead, not placed
        utPutDead(b);
    }
}

void initbugsbase(int N)
{
    int i;
    Bug * b;
    for(i=0; i<N; i++){
        b = randombugbase(1);        // 1 => alive, placed in nodes
        utPutAlive(b);
    }
    for(i=N; i<NMAX; i++){
        b = randombug(0);        // 0 => dead, not placed
        utPutDead(b);
    }
}


void splitbug(Bug *b)
{
    int tst,cnt;
    Bug * bb;
//    checkAlive();
    bb = utGetDead();           // now not dead but not yet alive... limbo
    copybug(b,bb);
    b->food /= 2.0;
    bb->food /= 2.0;
//    checkAlive();
    mutatebug(bb);
    mutatebug(b);               // mutate both children...
    tst = 0; cnt=0;
    while(tst == 0){
        cnt++;
        tst = jitterbug(bb);
        if(tst==-1){
            utPutDead(bb);      // back to dead
            break;
        }
        if(tst==1){
            utPutAlive(bb);     // made it to alive
            break;
        }
    }
//    checkAlive();
    return;                     // -1 => bug died during jittering
}

void killbug(Bug *b)
{
    int nn;
    nn = NODE(b->x,b->y);
//    assert(nodes[nn].bug == b);
//    nodes[nn].bug = 0;  bug might not have been placed yet...
    if(!utInAlive(b))
        fprintf(stderr,"Ack, trying to kill bug %d that is not alive.",(int) b);
    utDelAlive(b);
    utPutDead(b);
}

// -------------------- end of routines that use the hash sets

#define MAXTRY 2*NMAX

int choosemove()
{
    int ns,nn;
    ns = n_rand(2);         // could probably be more efficient here...
    nn=MAXMV-1;             // no zero => bug must move
    nn = n_rand(nn);
    return ns ? (1+nn) : -(1+nn);
}

Bug* randombug(int alive)
{
    Bug * b;
    int i,done,nn,ns;
    b = (Bug *) calloc(1,sizeof (Bug));
    b -> thisbug = b;
    b -> food = 1.0;
    for(i=0;i<NMOVE;i++){
        b->movex[i] = choosemove();
        b->movey[i] = choosemove();
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

Bug* randombugbase(int alive)
{                               // put all bugs on 1st row of lattice
    if(alive>0.95*ROWL){
        fprintf(stderr,"trying to put too many bugs on the base.\n");
        exit(2);
    }
    Bug * b;
    int i,done,nn,ns;
    b = (Bug *) calloc(1,sizeof (Bug));
    b -> thisbug = b;
    b -> food = 1.0;
    for(i=0;i<NMOVE;i++){
        b->movex[i] = choosemove();
        b->movey[i] = choosemove();
    }
    b->mutrate = mutrate;          // initialize to global for now...

    if(alive){
        b -> x = n_rand(ROWL);
        b -> y = 0;             // puts the bug on the base
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
    bb->x = b->x;    bb->y = b->y;
    bb->alive = b->alive;
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
            b->movex[i] = choosemove();
        ftmp = f_rand();
        if(ftmp < mutrate)
            b->movey[i] = choosemove();
    }
}
        

void movebug(Bug *b,int dx,int dy)
{
    int cnt,nn;
//    checkAlive();
    if(utInDead(b))             // in the unlikely event a dead bug is being asked to move...
        return;
    Bug * btmp;
    b->food -= movetax*(abs(dx)+abs(dy));
    if(b->food <0){
        killbug(b);
        nn = NODE(b->x,b->y);   // current node
        nodes[nn].bug=0;
        return;
    }
    nn = NODE(b->x,b->y);   // current node
    nodes[nn].bug=0;
    b->x = ADDX(b->x,dx);
    b->y = ADDY(b->y,dy);
    nn = NODE(b->x,b->y);   // new node
    btmp = nodes[nn].bug;   // old bug at new node (if present)
    nodes[nn].bug = b;      // install b at new node
    if(btmp != 0){          // find a new place for the old one
        int tst=0;
        while(tst == 0){
            tst = jitterbug(btmp);
            if(tst==-1){
                killbug(btmp);
                break;
            }
            if(tst==1){
                nn = NODE(btmp->x,btmp->y); // 
                nodes[nn].bug=btmp;         // don't use utPutAlive because btmp is already alive.
                break;
            }
        }
//        checkAlive();
        cnt = 1;                // for debug
    }
    if(nodes[nn].food>0)
        b->food += mouthfull;
    else
        b->food -= tax;
    if(b->food >1)
        splitbug(b);                
    if(b->food <0){
        killbug(b);
        nn = NODE(b->x,b->y);   // current node
        nodes[nn].bug=0;
        return;
    }
//    checkAlive();
}

int jitterbug(Bug *b)          // jitter x,y until find an empty spot
{                               // return 0 if still jittering, 1 if success
    int dx,dy,nn;
    dx = choosemove();
    dy = choosemove();
    b->food -= movetax*(abs(dx)+abs(dy));
    if(b->food<0){
        return -1;
    }
    b->x = ADDX(b->x,dx);
    b->y = ADDY(b->y,dy);
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
    doact(sense,dx,dy);
    movebug(b,dx,dy);
}
    
int bugNodes()
{
    int i,cnt;
    for(i=0,cnt=0; i<NMAX; i++)
        if(nodes[i].bug !=0)
            cnt++;
    return cnt;
}
int bugNotAlive()
{
    int i,cnt;
    for(i=0,cnt=0; i<NMAX; i++)
        if(nodes[i].bug>0)
           if(!utInAlive(nodes[i].bug))
            cnt++;
    return cnt;
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

int checkAlive()
{
    int cnt,cntt;
    cnt = bugNodes();
    cntt=bugNotAlive();
    if(Nalive-cnt>0 || cntt>0){
        fprintf(stderr,"Nalive = %d, %d onlattice.\n",Nalive,cnt);
        fprintf(stderr,"%d of %d on lattice not alive.\n",cntt,cnt);
        cnt=0;                  // for debug...
    }
}
