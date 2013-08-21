//  ising.c - the new moderne mac 2-d ising simulation
//
// 	started, september 15, 2000
//
//  monte.c - monte carlo ising spin updates...
//	october 6, 2000
//  281 hz w/out display... (mcarlo)
//  366 hz w/out display... (mcarlox1, mcarlox2)
//  458 hz using myrand1.h, rval locally declared (in mcarlox.c)...
//  ...speed temperature dependent!  above speeds w/ T = 2.5?
//  473 hz ZOOM=4  117 hz ZOOM=2  29 hz ZOOM=1
//  ...with mcarlox.f.c...
//  832 hz ZOOM=4  206 hz ZOOM=2  51 hz ZOOM=1
#include <stdio.h>
#include <math.h>
#include <fcntl.h>
#include "ising.h"
#include "glgraph.h"
#include "myrand4.h"

unsigned long Vout[SIZEX * SIZEY];			// output graphics image
unsigned long int _seed = 4;

Node nodes[NMAX], hlinks[NMAX], vlinks[NMAX];
unsigned char isPl[ROWL * NROWS];
unsigned long Rule[1024];			// rule table...
short rowl,nrows,depth,rowbytes;
float Temp,Beta;				// monte carlo parameters...
float Hfield = 0.01;
float Boltz[100];
unsigned long iBoltz[16];
long Nups,kval;
char pixname[32];
int fd;								// file descriptor for pix...
long nsteps;						// global step counter for display
long rtn,stepctl,altctl,altflg,oldn1,tempctl,pausectl; // for kbd control
long slowctl=1;
long ncount = 0;				// iteration counter
unsigned long int _seed;		// for myrand4.h
long energy[NMAX];
float mutrate=0.1;				// mutation rate for diffusing bonds
float diffrate=0.0;
long driveper;
long tsctl,displayctl, transient;

void Display()
{
	int i,j;

	mcarlosg(0);	// checkerboard one parity
	mcarlosg(1);	// checkerboard other parity
	vdiffuse(diffrate);
	hdiffuse(diffrate);
	++ncount; ++nsteps;
	if(nsteps%slowctl ==0){
		display();
	}
	if(nsteps>transient){
		if(driveper>0){
			if(nsteps%driveper == 0){
				Hfield = -Hfield;
				ldboltz();
			}
		}
	}
	prenergy();
	glutSwapBuffers();
	glutPostRedisplay();	// maybe slightly faster after glutSwapBuffers()
	++gl_framecount;
}

//int main(int ac, char **av)
int main (int argc, const char * argv[])
{
	float xx,yy;
	long i;
    glutInit(&argc, (char**) argv);
	initnodescb(nodes);			// also inits the Elinks...
	initnodescb(hlinks);
	initnodescb(vlinks);
	mtinit(argc,argv);
	fprintf(stderr,"Transient...");
	for(i=0;i<transient;i++){
		mcarlosg(0); mcarlosg(1);
	}
	fprintf(stderr," done.\n");

//	setnodes(hlinks,1);
//	setnodes(vlinks,1);

    prefsize(SIZEX,SIZEY);
	initgraph("Driven Spin Glass!");
    yy = 1.2; xx = yy * XFAC;
    scale(-xx,xx,-yy,yy);
	
	glutMainLoop( );
return 0;
}

int countem(Node *nn)
{
	int i,sum;
	for(sum=0,i=0;i<NMAX;i++)
		if(nn[i].occ>0) sum++;
	return sum;
}

void prnd(){
	int i;
	double fr;
	for(i=0;i<100;i++){
		fr=f_rand();
		printf("%f\t",fr);
	}
}

	
