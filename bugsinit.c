
//  ising simulation initialization routines...

#include <unistd.h>				// for getopt
#include <stdio.h>
#include <math.h>
#include "bugs.h"

//static short oldepth;

void usage()
{
	fprintf(stderr,"-r  random number seed\n");
	fprintf(stderr,"-t  number of time steps [10000]\n");
	fprintf(stderr,"-n  number of transient time steps [0]\n");
	fprintf(stderr,"-M  move tax (per step) [0.01]\n");
	fprintf(stderr,"-m  mutation rate [0.05]\n");
	fprintf(stderr,"-f  food in a mouthful [0.1]\n");
	fprintf(stderr,"-x  tax when no food [0.0]\n");
    fprintf(stderr,"-N  number of initial bugs [1000]\n");
}


void bugsinit(int ac, char *av[])
{
	char c;
    //     initial values:
	_seed=time(0);					// every run random
	nsteps = 10000;
    mutrate = 0.05;
    mouthfull = 0.1;
    movetax = 0.01;
    transient = 0;
    ninit = 1000;
    tax = 0.0;

// end default... now change if option passed.........
    while ((c = getopt(ac, (char **) av, "s:t:n:M:m:f:x:N:h")) != -1) {
		switch(c) {
		case 's':
			_seed = atoi(optarg); // random number seed
			break;
		case 't':				// number of time steps
			nsteps = atoi(optarg);
			break;
		case 'n':				// transient time
			transient = atoi(optarg);
			break;
        case 'M':
            movetax = atof(optarg);
            break;
        case 'm':
            mutrate = atof(optarg);
            break;
        case 'f':
            mouthfull = atof(optarg);
            break;
        case 'x':
            tax = atof(optarg);
            break;
        case 'N':
            break;
        case 'h':
			usage();
			exit(0);
		}
    }
    initpop();
    initact();
	initnodescb(nodes);			// initializes neighbors
    initfoodtree(nodes);
    initbugs(ninit);
}


// fill in node structure neighborhoods...

// circular boundary conditions...
void initnodescb(Node * nn)
{
	long i,idx;

// just to initialize to an Ising ground state...
	for(i=0;i<NMAX;i++){
		nn[i].occ = -1;
        nn[i].bug = NULL;
        nn[i].food = 0;
    }

// bottom neighbor...
// lower vlink
// LR diag
	for(i=0;i<ROWL;i++){
		nn[i].Nbrs[0] = (NROWS-1)*ROWL + i;
	}
	for(i=ROWL;i<ROWL*NROWS;i++){
		nn[i].Nbrs[0] = i - ROWL;
	}
	
// right neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if((i+1)%ROWL == 0){	// far R column
			nn[i].Nbrs[1] = i+1-ROWL;
		}
		else{
			nn[i].Nbrs[1] = i+1;
			if(i+1+ROWL>NMAX){	// off top
				idx = i + 1 + ROWL-NMAX;
			}
		}
	}

// top neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i+ROWL >= NMAX){		// top row
			nn[i].Nbrs[2] = (i%ROWL);
		}
		else{
			nn[i].Nbrs[2] = i+ROWL;
		} 
	}

// left neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i%ROWL == 0){
			nn[i].Nbrs[3] = i+ROWL-1;
		}
		else{
			nn[i].Nbrs[3] = i-1;
		}
	}
}

// circular boundary conditions left and right,
// solid boundary top and bottom.
void initnodescb1(Node * nn)
{
	long i;

// -1 means node unoccupied...
	for(i=0;i<NMAX;i++)
		nn[i].occ = -1;

// bottom neighbor...
	for(i=0;i<ROWL;i++)
		nn[i].Nbrs[0] = -1;
	for(i=ROWL;i<ROWL*NROWS;i++)
		nn[i].Nbrs[0] = i - ROWL;
	
// right neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if((i+1)%ROWL == 0)
			nn[i].Nbrs[1] = i+1-ROWL;
		else
			nn[i].Nbrs[1] = i+1;
	}

// top neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i+ROWL >= NMAX)
			nn[i].Nbrs[2] = -1;
		else
			nn[i].Nbrs[2] = i+ROWL;
	}

// left neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i%ROWL == 0)
			nn[i].Nbrs[3] = i+ROWL-1;
		else
			nn[i].Nbrs[3] = i-1;
	}
}

void setnodes(Node * nn,int val)
{
	int i;
	for(i=0; i<NMAX; i++)
		nn[i].occ=val;
}

void rannodes(Node *nn, float dens)
{
	int i;
	float ftmp;
	for(i=0;i<NMAX; i++){
		ftmp = f_rand();
		if(ftmp<dens)
			nn[i].occ=-1;
		else
			nn[i].occ=1;
	}
}
		
void pnodes(Node *nn, int start)
{
	int i,j;
	for(i=0; i<10; i++){
		for(j = 0; j<10; j++){
			if(nn[start+i*ROWL + j].occ==-1)
				printf("-1\t");
			else
				printf("1\t");
		}
		printf("\n");
	}
}

//void penergy(int idx);

void initfoodgrad(Node *nn)
{
    int i,j;
    double mx;
    mx = sqrt(ROWL*ROWL + NROWS*NROWS);

    for(i=0;i<NROWS;i++){
        for(j=0;j<ROWL;j++){
            if(i<NROWS/2)
                nn[i*ROWL+j].food = 255*i/(NROWS/2);
            else
                nn[i*ROWL+j].food = (NROWS-i)*255/(NROWS/2);
        }
    }
}
 
void initfoodtree(Node *nn)
{
    int i,j,nbranch,brspace, idx;

    brspace = 10;
    nbranch = 1;
    for(i=0;i<NROWS;i++){
        if(i==0){
            for(j=0;j<ROWL;j++){
                idx = i*ROWL+j;
                nn[idx].food = 1.0;
            }
            continue;
        }
        for(j=0;j<nbranch;j++){
            idx = i*ROWL+ROWL/2+j*brspace;
            nn[idx].food = 1.0;
            idx = i*ROWL+ROWL/2-j*brspace;
            nn[idx].food = 1.0;
        }
        if(i%(2*brspace) == 0){
            for(j=ROWL/2-(nbranch*brspace);j<ROWL/2+(nbranch*brspace);j++){
                idx = i*ROWL+j;
                nn[idx].food = 1.0;
            }
            nbranch++;
        }
        if(nbranch>12)
            break;
    }
}

#include <fcntl.h>
int pipe_pop;

void initpop()
{
//    system("rm -f /tmp/population; mkfifo -m 666 /tmp/population");
    pipe_pop = open("/tmp/population",O_WRONLY);
    if(pipe_pop<0) perror("Did not find population pipe.\n(someone needs to execute mkfifo /tmp/population)\n");
//    system("graph.py population &");
}

void outputpop()
{
    char out[256];
    sprintf(out,"%d\n",Nalive);
    write(pipe_pop,out,strlen(out));
}


    
