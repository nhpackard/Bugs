#include <stdio.h>
#include "bugs.h"

void utInitAlive()
{
}



void utPutAlive(Bug * b)
{
    Bug * bb;
    int nn;
    HASH_FIND(hha,Alive,&b,sizeof(Bug *),bb);
    if(bb==NULL){
        HASH_ADD(hha,Alive,thisbug,sizeof(Bug *),b);
        Nalive++;
    }
    else
        fprintf(stderr,"PutAlive warning:  Bug %d already exists.\n",(unsigned int) b);
    nn = NODE(b->x,b->y);
    if(nodes[nn].bug !=NULL){
        fprintf(stderr,"PutAlive:  called on a filled site.\n");
    }
    nodes[nn].bug = b;
}

void utDelAlive(Bug * b)
{
    int n1,n2;
    n1 = HASH_CNT(hha,Alive);
    HASH_DELETE(hha,Alive,b);
    Nalive--;
    n2 = HASH_CNT(hha,Alive);
    if(n2 != n1-1)
        fprintf(stderr,"prob with Alive hash table.\n");
    n2 = cntAliveIter();
    if(n2 != n1-1)
        fprintf(stderr,"prob with Alive hash table... caught by HASH_ITER.\n");
    if(utInAliveIter(b)){
        fprintf(stderr,"utDelAlive: deleted bug found by inAliveIter.\n");
        n1=1;                   // for debug stop
    }
    if(utInAlive(b)!=utInAliveIter(b)){
        fprintf(stderr,"utDelAlive: deleted bug found by inAliveIter.\n");
        n1 = 1;
    }

}

int utInAlive(Bug * b)
{
    Bug *bb;
    HASH_FIND(hha,Alive,&b,sizeof(Bug *),bb);
    if(bb) return 1;
    else return 0;
}
int utInAliveIter(Bug * b)
{
    int cnt;
    Bug *bb,*btmp;
    cnt = 0;
    HASH_ITER(hha,Alive,bb,btmp){
        if(bb==b)
            return(1);
    }
    return 0;
}

int utInDead(Bug * b)
{
    Bug *bb;
    HASH_FIND(hhd,Dead,&b,sizeof(Bug *),bb);
    if(bb) return 1;
    else return 0;
}


void utInitDead()
{
}

void utPutDead(Bug * b)
{
    Bug * bb;
    int n1;
    HASH_FIND(hhd,Dead,&b,sizeof(Bug *),bb);
    if(bb==NULL){
        HASH_ADD(hhd,Dead,thisbug,sizeof(Bug *),b);
        Ndead++;
    }
    else
        fprintf(stderr,"warning:  Bug %d already dead.\n",(unsigned int) b);
    if(utInAlive(b)!=utInAliveIter(b)){
        fprintf(stderr,"utDelAlive: deleted bug found by inAliveIter.\n");
        n1 = 1;
    }

}

void utDelDead(Bug * b)
{
    int n1,n2;
    n1 = HASH_CNT(hhd,Dead);
    HASH_DELETE(hhd,Dead,b);
    n2 = HASH_CNT(hhd,Dead);
    if(n2 != n1-1)
        fprintf(stderr,"prob with Dead hash table.\n");
    Ndead--;
}

Bug * utGetDead()
{
    Bug * b;
    int n1,n2;
    n1 = HASH_CNT(hhd,Dead);

    b = Dead->hhd.next;         // this actually gets the 2nd bug from Dead.  could b=Dead?
    if(b==NULL){
        fprintf(stderr,"ran out of bugs...\n");
        return NULL;
    }
    HASH_DELETE(hhd,Dead,b);
    n2 = HASH_CNT(hhd,Dead);
    if(n2 != n1-1)
        fprintf(stderr,"prob with Dead hash table.\n");
    Ndead--;
    return (Bug *) b;
}

void checkDead()
{
    int cnt;
    Bug *b, *btmp;
    cnt = 0;
    HASH_ITER(hhd,Dead,b,btmp){
        if(utInAlive(b)) cnt++;
    }
    fprintf(stderr,"%d dead found in alive.\n",cnt);
}

    


int checkbugs()
{
    int i,cnt;
    int tmp;
    for(i=0,cnt=0; i<NMAX; i++)
        if(nodes[i].bug !=0)
            cnt++;
    if(Nalive!=cnt)
        return(1);
    if(Ndead != NMAX-cnt)
        return(2);

    // checkhash:
    int alivesiz, deadsiz,aliveiter;
    alivesiz = HASH_CNT(hha,Alive);
    deadsiz = HASH_CNT(hhd,Dead);
    aliveiter = cntAliveIter();
    if(alivesiz != Nalive)
        return(3);
    if(aliveiter != Nalive)
        return(4);
    if(deadsiz != Ndead)
        return(5);
    return(0);

}


Bug * bpt[NMAX];                // for iterating safely

void updatebugs()
{
    static int curidx=0;
    int nalive,i,tmp,nxtidx;
    Bug *b,*btmp;
    nalive = HASH_CNT(hha,Alive);
    i=0;
    HASH_ITER(hha, Alive, b, btmp) {
        tmp = utInAlive(b);     // uses Alive, Dead
        if(tmp!=1){
            fprintf(stderr,"tmp=%d, InAlive=%d, InAliveIter=%d\n",tmp,utInAlive(b),utInAliveIter(b));
            fprintf(stderr,"Nalive=%d, cntAlive=%d, cntAliveIter=%d\n",Nalive,cntAlive(b),cntAliveIter(b));
            assert(tmp==1);
        }
        sensemove(b);           // uses Alive, Dead
        i++;
    }
    HASH_ITER(hha, Alive, b, btmp) { // go through the whole list again,
        b->alive=1;                  // mark all the newborns as alive.
    }
    curidx = nxtidx;
    if(Nalive==0){
        fprintf(stderr,"all dead!\n");
        exit(0);
    }
}

////////////////////////////////////////////////////////
// Activity stuff...


#include <fcntl.h>
int pipe_act;

typedef struct{
    int sense;
    int movex;
    int movey;
} Actkey;

typedef struct{
    UT_hash_handle hhact;
    Actkey key;
    int count;
    int time;
} Activity;

Activity * activity = NULL;

void initact()
{
    pipe_act = open("/tmp/activity",O_WRONLY);
    if(pipe_act<0) perror("Did not find activity pipe.\n(someone needs to execute mkfifo /tmp/activity)\n");
}


void doact(int sense, int movex, int movey)
{
    Activity *aa;
    Actkey key;
    key.sense = sense;
    key.movex = movex;
    key.movey = movey;

    HASH_FIND(hhact,activity,&key,sizeof(Actkey),aa);
    if(aa){                     // found
        aa->count++;
    }
    else{                       // not found => new key
        aa = (Activity *) calloc(1,sizeof(Activity));
        aa->key = key;
        aa->count = 1;
        HASH_ADD(hhact,activity,key,sizeof(Actkey),aa);
    }
    aa->time = ncount;
}

void outputact()
{
    Activity *a, *atmp;
    static char out[512];
    int cnt;
    cnt = 0;
    HASH_ITER(hhact,activity,a,atmp){
        if(a->time == ncount-1){  // for version that only prints out contemporary activity...
            sprintf(out,"%d-%d-%d %d ", // for new graphactivity.py that takes 'tag1 count1 tag2 count2 ...'
                    a->key.sense,a->key.movex,a->key.movey,a->count);
            write(pipe_act,out,strlen(out));
            if(++cnt>10000)
                break;
        }
    }
    sprintf(out,"\n");
    write(pipe_act,out,strlen(out));
}

/**********
counting utilities
*********/

int cntActivity()
{
    Activity *a, *atmp;
    static char out[512];
    int cnt;
    cnt = 0;
    HASH_ITER(hhact,activity,a,atmp){
        cnt++;
    }
    return(cnt);
}

int cntNotAlive()
{
    int i,cnt;
    for(i=0,cnt=0; i<NMAX; i++)
        if(nodes[i].bug>0)
           if(!utInAlive(nodes[i].bug))
            cnt++;
    return cnt;
}
int cntAlive()
{
    return(HASH_CNT(hha,Alive));
}


int cntAliveIter()
{
    int cnt;
    Bug *b, *btmp;
    cnt = 0;
    HASH_ITER(hha,Alive,b,btmp){
        if(utInAlive(b)==0)
            continue;
        cnt++;
    }
    return(cnt);
}
int cntDead()
{
    int cnt;
    Bug *b, *btmp;
    cnt = 0;
    HASH_ITER(hhd,Dead,b,btmp){
        cnt++;
    }
    return(cnt);
}

int checkAlive()
{
    int cnt,cntt;
    cnt = bugNodes();
    cntt=cntNotAlive();
    if(Nalive-cnt>0 || cntt>0){
        fprintf(stderr,"Nalive = %d, %d onlattice.\n",Nalive,cnt);
        fprintf(stderr,"%d of %d on lattice not alive.\n",cntt,cnt);
        cnt=0;                  // for debug...
    }
}
