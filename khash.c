#include <stdio.h>
#include "khash.h"
#include "bugs.h"

KHASH_MAP_INIT_STR(Act, int)
KHASH_SET_INIT_INT(Alive)
KHASH_SET_INIT_INT(Dead)

void hashinit()
{
    khInitAct();
    khInitAlive();
    khInitDead();
}

khash_t(Act) *hact;

void khInitAct()
{
    hact = kh_init(Act);
}

void khPutAct(char * key, int val)
{
    khiter_t k;
    int ret;
    k = kh_get(Act,hact,key);
    if(k == kh_end(hact)){
        k = kh_put(Act, hact, key, &ret);
    }
    kh_value(hact,k) = val;
}

int khGetAct(char * key)
{
    khiter_t k;
    int v;
    k = kh_get(Act, hact, key);
    v = kh_value(hact,k);
    return(v);
}

void khIncAct(char * key)
{
    int tmp;
    khiter_t k;
    k = kh_get(Act,hact,key);
    if(kh_exist(hact,k)){
        tmp = khGetAct(key);
        tmp++;
    }
    else
        tmp = 1;
    khPutAct(key,tmp);
}

void khPrintallAct(FILE *fp)
{
    const char *key;
    int var;
    kh_foreach(hact,key,var,{fprintf(fp,"%s  %d\n",key,var);});
}


/**********************
int main(){
	int ret;
    int i;
    char **str;


    khInit();
    str = (char **) calloc(40,sizeof(char *));
    for(i=0;i<40;i++){
        str[i] = (char *)calloc(40,sizeof(char));
        sprintf(str[i],"%d.%d",i,3*i);
    }
    for(i=0;i<40;i++){
        khPut(str[i],10*i);
    }
    khPrintall(stdout);
}
*************************/


khash_t(Alive) *halive;

void khInitAlive()
{
    halive = kh_init(Alive);
    kh_resize(Alive,halive,NMAX);
}

void khPutAlive(Bug * b)
{
    unsigned int key;
    khiter_t k;
    int ret,nn;

    key =  b;
    k = kh_get(Alive,halive,key);
    if(k == kh_end(halive)){         // if key not found
        k = kh_put(Alive, halive, key, &ret);
        nn = NODE(b->x,b->y);
        if(nodes[nn].bug != NULL)
            fprintf(stderr,"warning: khPutAlive overwriting a bug on node %d\n",nn);
        nodes[nn].bug=b;
        Nalive++;
    }
    else
        fprintf(stderr,"warning:  Bug %d already exists.\n",key);
}

void khDelAlive(Bug * b)
{
    int ret,nn;
    unsigned int key;
    khiter_t k;
    key =  (unsigned int) b;
    k = kh_get(Alive,halive,key);
    kh_del(Alive,halive,k);
    nn = NODE(b->x,b->y);
    nodes[nn].bug=NULL;
    Nalive--;
}

int khInAlive(Bug *b)
{
    unsigned int key;
    khiter_t k;
    int ret,nn;

    key =  (unsigned int ) b;
    k = kh_get(Alive,halive,key);
    if(k == kh_end(halive))         // if key not found
        return 0;
    else
        return 1;               // key found
}
    


khash_t(Dead) *hdead;

void khInitDead()
{
    hdead = kh_init(Dead);
    kh_resize(Dead,hdead,NMAX);
}

void khPutDead(Bug * b)
{
    unsigned int key;
    khiter_t k;
    int ret;

    key =  (unsigned int)b;
    k = kh_put(Dead, hdead, key, &ret);
    if(ret==0)
        fprintf(stderr,"warning:  Bug %d already dead.\n",key);
    else
        Ndead++;
}

void khDelDead(Bug * b)
{
    int ret;
    unsigned int key;
    khiter_t k;
    key = b;
    k = kh_get(Dead,hdead,key);
    kh_del(Dead,hdead,k);
    Ndead--;
//    if(ret==0)
//        fprintf(stderr,"warning:  Bug %d not found to be deleted.\n",key)
}

Bug * khGetDead()
{
    unsigned int key;
    khint_t k;
    k = kh_begin(hdead);
    key = kh_key(hdead,k);
    kh_del(Dead,hdead,k);
    Ndead--;
    return (Bug *) key;
}

int khInDead(Bug *b)
{
    unsigned int key;
    khiter_t k;
    int ret,nn;

    key =  (unsigned int ) b;
    k = kh_get(Dead,hdead,key);
    if(k == kh_end(hdead))         // if key not found
        return 0;
    else
        return 1;               // key found
}

void checkhash()
{
    khint_t alivesiz,deadsiz;
    alivesiz = kh_size(halive);
    deadsiz = kh_size(hdead);
    printf("\n%d alive\n%d dead\n",alivesiz,deadsiz);
}

void checkDead()
{
    int i;
    int key,var,cnt;
    Bug *b;
    cnt = 0;
    kh_foreachkey(hdead,key,{b = (Bug *) key; if(khInAlive(b)) cnt++;});
    printf("%d dead found in alive.\n");
}


void updatebugs()
{
    int i;
    int key,var;
    Bug *b;
    kh_foreachkey(halive,key,{b = (Bug *) key; sensemove(b);});
//    printf("%d alive\n%d dead\n",Nalive,Ndead);
}

