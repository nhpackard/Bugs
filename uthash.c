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
        fprintf(stderr,"warning:  Bug %d already exists.\n",(unsigned int) b);
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
}

int utInAlive(Bug * b)
{
    Bug *bb;
    HASH_FIND(hha,Alive,&b,sizeof(Bug *),bb);
    if(bb) return 1;
    else return 0;
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
    HASH_FIND(hhd,Dead,&b,sizeof(Bug *),bb);
    if(bb==NULL){
        HASH_ADD(hhd,Dead,thisbug,sizeof(Bug *),b);
        Ndead++;
    }
    else
        fprintf(stderr,"warning:  Bug %d already dead.\n",(unsigned int) b);
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

    

void checkhash()
{
    int alivesiz, deadsiz;
    alivesiz = HASH_CNT(hha,Alive);
    deadsiz = HASH_CNT(hhd,Dead);
    printf("\n%d alive\n%d dead\n",alivesiz,deadsiz);
}

Bug * bpt[NMAX];                // for iterating safely

void updatebugs()
{
    int nalive,i;
    Bug *b,*btmp;
    nalive = HASH_CNT(hha,Alive);
    i=0;
    HASH_ITER(hha, Alive, b, btmp) {
        sensemove(b);
        i++;
    }
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
            sprintf(out,"%d %d %d %d ",
                    a->key.sense,a->key.movex,a->key.movey,a->count);
            write(pipe_act,out,strlen(out));
            if(++cnt>10000)
                break;
        }
    }
    sprintf(out,"\n");
    write(pipe_act,out,strlen(out));
}
