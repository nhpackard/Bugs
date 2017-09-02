
#include <stdio.h>
#include <math.h>
#include <fcntl.h>
#include "glgraph.h"

#include "bugs.h"


int ncount=0, nsteps=0;
int slowctl = 10;
int pausectl = 0;
int datactl = 10;
int transient = 0;

Bug * Alive = NULL;
Bug * Dead  = NULL;
Bug * btst;
Node nodes[NMAX];
int Nalive, Ndead;
int pipe_pop;

//unsigned short Vout[SIZEX * SIZEY];
unsigned long Vout[SIZEX * SIZEY];
unsigned long int _seed = 0;

// initialize following in bugsinit.c
double mutrate;
double mouthfull;
double movetax,tax;
int ninit;


void Display()
{
    updatebugs();
	++ncount; ++nsteps;
    if(ncount%datactl == 0){
        outputpop();
        outputact();
    }
	if(nsteps%slowctl ==0)
		display();
	glutSwapBuffers();
	glutPostRedisplay();	// maybe slightly faster after glutSwapBuffers()
	++gl_framecount;
//    if(ncount%100==0)
//        scanf("%d",&i);
}


int main(int ac,char **av){
    int i;

    fprintf(stderr,"Bugs!\n");

	float xx,yy;

	glutInit(&ac, (char**) av);
    bugsinit(ac,av);

//    for(i=0;i<NROWS;i++)
//        nodes[i*ROWL+NROWS/2].food=i;
//    for(i=0;i<ROWL;i++)
//        nodes[ROWL*(NROWS/2)+i].food=i;
//	mtinit(ac,av);
	fprintf(stderr,"Transient...");
	for(i=0;i<transient;i++){
        updatebugs();
	}
	fprintf(stderr,"transient done.\n");

    prefsize(SIZEX,SIZEY);
	initgraph("Bugs!");
    yy = 1.2; xx = yy * XFAC;
    scale(-xx,xx,-yy,yy);

	
	glutMainLoop( );
return 0;
}
