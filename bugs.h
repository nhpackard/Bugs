#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "myrand4.h"
#include "uthash.h"

#define REAL double
#define RES 0		// resolution switch...

#define RES 0		// resolution switch...
#if RES == 0
#define CELLSZ 0.01
//#define CELLSZ (.01*256.0/360.0)
#endif
#if RES == 1
#define CELLSZ .02
#endif
#if RES == 2
#define CELLSZ .04
#endif
#if RES == 3
#define CELLSZ .08
#endif
//#define SIZEX 768
//#define SIZEY 512
//#define SIZEY 480
#define SIZEX 720
#define SIZEY 480
#define ROWL 300
#define NROWS 200

//#define SIZEX 632
//#define SIZEY 632
//#define ROWL 256
//#define NROWS 256
#define XFAC (REAL)SIZEX/SIZEY
#define NMAX NROWS*ROWL
#define NNBRS 9			// neighbors of nodes!



 /*****
 neighborhood shape is

8 1 5

4 0 2

6 3 5

  ********/



#define ADDX(x,dx)  (((x)+(dx))<0 ? ((x)+(dx)) + ROWL : ((x)+(dx))%ROWL)
#define ADDY(y,dy)  (((y)+(dy))<0 ? ((y)+(dy)) + NROWS : ((y)+(dy))%NROWS)
#define NODE(x,y) ((y)*ROWL + (x))

#define NMOVE 512               // size of the brain:  map from nbhd config to motion vectors
#define MAXMV 4

typedef struct {
    // for uthash
    void * thisbug;              /* key */
    UT_hash_handle hha,hhd;          /* makes this structure hashable */
    // 
    double food;
    int x,y;
    int alive;
    int movex[NMOVE];              // 9 site nbrhood
    int movey[NMOVE];              // 9 site nbrhood
    int act[NMOVE];
    double mutrate;
} Bug;

typedef struct {
    Bug* bug;
    double food;
	long occ;
	long Nbrs[NNBRS];	// list of neighbors
} Node;

extern int ncount, nsteps;
extern int slowctl;
extern int transient;

extern Bug * Alive;
extern Bug * Dead;
extern Bug * btst;
extern Node nodes[];
extern int Nalive, Ndead;
extern int ninit;

extern void sgcolor_init();
extern void sgcolor(long,long,long);
extern unsigned long Vout[];
extern double mutrate;
extern double mouthfull ;
extern double movetax ;
extern double tax;


// displays.c
extern void bugcolor_init();
extern void bugcolor(double , double);

// inits.c
extern void initfoodsquare(Node *);
extern void initfoodtree(Node *);
extern void initfoodboxes(Node *);

// bugutil.c
extern Bug* randombug(int alive);
extern Bug* randombugbase(int alive);
extern void initbugs(int N);
extern void initbugsbase(int N);
extern void copybug(Bug *b, Bug *bb);
extern void killbug(Bug *b);
extern void movebug(Bug *b,int dx,int dy);
extern int  jitterbug(Bug *b);          // jitter x,y until find an empty spot
extern void sensemove(Bug *b);
extern void splitbug(Bug *b);
extern void mutatebug(Bug *b);

// khash.c
extern void updatebugs();
extern void khPutAct(char * key, int val);
extern void khInitAct();
extern int khGetAct(char * key);
extern int khGetAct(char * key);
extern void khIncAct(char * key);
extern void khPrintallAct(FILE *fp);
extern void khInitAlive();
extern void khPutAlive(Bug * b);
extern void khDelAlive(Bug * b);
extern void khInitDead();
extern void khPutDead(Bug * b);
extern void khDelDead(Bug * b);
extern Bug * khGetDead();

// uthash.c
extern void initact();
extern void doact(int sense, int movex, int movey);
extern void outputact();
extern void utInitAlive();
extern void utPutAlive(Bug * b);
extern void utInitDead();
extern void utDelAlive(Bug * b);
extern void utPutDead(Bug * b);
extern void utDelDead(Bug * b);
extern Bug * utGetDead();
extern int utInAlive(Bug * b);
extern int utInDead(Bug * b);
extern void checkhash();

// displays.c
extern void display();

//inits.c
extern void initnodescb(Node * nn);
extern void initnodescb1(Node * nn);
extern void setnodes(Node * nn,int val);
extern void rannodes(Node *nn, float dens);
extern void pnodes(Node *nn, int start);
extern void initfoodgrad(Node *nn);
extern void initfoodtree(Node *nn);
extern void initpop();
extern void outputpop();

// bugsinit.c
extern void bugsinit(int ac, char *av[]);
