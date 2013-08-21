
#include <stdio.h>
#include "bugs.h"
#include "glgraph.h"

#if 0
#if RES == 0
#define CELLSZ (2.0/ROWL)
#define SZ1 0   
#define SZ2 2
#define SZM1 0
#define SZM2 2
#define YDISP 2
#endif
#endif

int slowctl, ncount;
unsigned long Vout[SIZEX*SIZEY];

void display()
{
    long i;
	static int first=1;
/*
	if(first){
		bugcolor_init();
		first=0;
	}
*/	
    color(RED);
    clear();
//	for(i=0; i<NMAX; i++)
//            drawnodebug(i);
//    border();
//	drawbuffer();
}



void Display()
{
    display();
	glutSwapBuffers();
	glutPostRedisplay();	// maybe slightly faster after glutSwapBuffers()
	++gl_framecount;
}


main(int ac,char **av){
    int i;
    double xx,yy;

    printf("Bugs!");

	glutInit(&ac, (char**) av);
//	initnodescb(nodes);			// initializes neighbors
//    initfoodtree(nodes);
//    initbugs(1000);

//    for(i=0;i<NROWS;i++)
//        nodes[i*ROWL+NROWS/2].food=i;
//    for(i=0;i<ROWL;i++)
//        nodes[ROWL*(NROWS/2)+i].food=i;
//	mtinit(ac,av);

    prefsize(SIZEX,SIZEY);
	initgraph("Bugs!");
    yy = 1.0; xx = yy * XFAC;
    scale(-xx,xx,-yy,yy);
	
	glutMainLoop( );
return 0;
}
