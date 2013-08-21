
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
	fprintf(stderr,"-X  move tax (per step) [0.01]\n");
	fprintf(stderr,"-m  mutation rate [0.05]\n");
	fprintf(stderr,"-f  food in a mouthful [0.8]\n");
	fprintf(stderr,"-x  tax when no food [0.0]\n");
    fprintf(stderr,"-N  number of initial bugs [100]\n");
    fprintf(stderr,"-b  initial distribution [0]:\n\t 0=random placement, 1 random placement on base\n");
    fprintf(stderr,"-F  food nitial distribution [0]:\n\t 0=square, 1 tree\n");
}


void bugsinit(int ac, char *av[])
{
	char c;
    int basectl;
    int foodctl;
    //     initial values:
	_seed=time(0);					// every run random
	nsteps = 10000;
    mutrate = 0.05;
    mouthfull = 0.8;
    movetax = 0.01;
    transient = 0;
    ninit = 100;
    tax = 0.0;
    basectl = 0;
    foodctl = 2;

// end default... now change if option passed.........
    while ((c = getopt(ac, (char **) av, "s:t:n:X:m:f:x:N:b:F:h")) != -1) {
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
        case 'X':
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
            ninit = atoi(optarg);
            break;
        case 'b':
            basectl = atoi(optarg);
            break;
        case 'F':
            foodctl = atoi(optarg);
            break;
        case 'h':
        default:
			usage();
			exit(0);
		}
    }
    initpop();
    initact();
	initnodescb(nodes);			// initializes neighbors
    switch(basectl){
    case 1:
        initbugsbase(ninit);
        break;
    default:
    case 0:
        initbugs(ninit);
    }
    switch(foodctl){
    case 0:
        initfoodsquare(nodes);
        break;
    case 1:
        initfoodtree(nodes);
        break;
    default:
    case 2:
        initfoodboxes(nodes);
        break;
    }
}


/*****
Neighborhood:

8 1 5

4 0 2

6 3 5

*****/


// fill in node structure neighborhoods...

// circular boundary conditions...
void initnodescb(Node * nn)
{
	long i,idx;

// center cell...
    for(i=0; i<NMAX; i++){
        nn[i].Nbrs[0] = i;
        nn[i].bug = NULL;
        nn[i].food = 0;
    }

// top neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i+ROWL >= NMAX){		// top row
			nn[i].Nbrs[1] = (i%ROWL);
		}
		else{
			nn[i].Nbrs[1] = i+ROWL;
		} 
	}

// right neighbor...
	for(i=0; i<ROWL*NROWS; i++)
	{
		if((i+1)%ROWL == 0){	// far R column
			nn[i].Nbrs[2] = i+1-ROWL;
		}
		else{
            if(i == NMAX-1)     // UR corner
                nn[i].Nbrs[2] = 0;
            else
                nn[i].Nbrs[2] = i+1;
        }
    }
// bottom neighbor...
	for(i=0;i<ROWL;i++){
		nn[i].Nbrs[3] = (NROWS-1)*ROWL + i;
	}
	for(i=ROWL;i<ROWL*NROWS;i++){
		nn[i].Nbrs[3] = i - ROWL;
	}
	


// left neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i%ROWL == 0){
			nn[i].Nbrs[4] = i+ROWL-1;
		}
		else{
			nn[i].Nbrs[4] = i-1;
		}
	}
// UR neighbor...
	for(i=0;i<ROWL*NROWS;i++){
        if(i+ROWL >= NMAX ){
            if(i == NMAX/1)       // UR corner
                nn[i].Nbrs[5] = 0;
            else
                nn[i].Nbrs[5] = i+ROWL+1-NMAX;
        }
        else{
            if((i+1)%ROWL == 0)	// far R column
                nn[i].Nbrs[5] = i+1;
            else
                nn[i].Nbrs[5] = i+ROWL+1;
        }
	}
// LR neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i < ROWL){
            if(i==ROWL-1)       // LR corner
                nn[i].Nbrs[6] = NMAX-ROWL;
            else
                nn[i].Nbrs[6] = i+NMAX-ROWL+1;
        }
		else{
            if((i+1)%ROWL == 0)	// far R column
                nn[i].Nbrs[6] = i-1;
            else
                nn[i].Nbrs[6] = i-ROWL+1;
        }
	}
// LL neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i<ROWL){             // bottom row
            if(i==0)            // LL corner
                nn[i].Nbrs[7] = NMAX-1;
            else
                nn[i].Nbrs[7] = i+NMAX-ROWL-1;
        }
		else{
            if(i%ROWL == 0)     // L column
                nn[i].Nbrs[7] = i-1;
            else
                nn[i].Nbrs[7] = i-ROWL-1;
        }
	}
// UL neighbor...
	for(i=0;i<ROWL*NROWS;i++)
	{
		if(i+ROWL > NMAX){
			if(i==NMAX-ROWL)    // UL corner
                nn[i].Nbrs[8] = ROWL-1;
			nn[i].Nbrs[8] = i+ROWL-NMAX-1;
        }
		else{
            if(i%ROWL == 0)     // L column
                nn[i].Nbrs[8] = i+1;
            else
                nn[i].Nbrs[8] = i+ROWL-1;
        }
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
 
void initfoodsquare(Node *nn)
{
    int i,lside,rside,top;
    lside = ROWL/4;
    rside = 3*ROWL/4;
    top=ROWL/2;
    for(i=lside; i<rside; i++){
        nn[i].food = 0.3;
        nn[top*ROWL+i].food = 0.3;
    }
    for(i=0; i<top; i++){
        nn[i*ROWL+lside].food = 0.3;
        nn[i*ROWL+rside].food = 0.3;
    }
}


void initfoodboxes(Node *nn)
{
    int i,j,spacex,spacey,bsize,kk,k,idx,bspace;

    bsize = 3;
    bspace = 2;
    spacey = bspace;
    for(j=0;j<NROWS;j+=spacey+bspace){
        spacex = bspace;
        for(i=0;i<ROWL;i+=spacex+bspace){
            for(kk=0;kk<bsize;kk++){
                for(k=0;k<bsize;k++){
                    idx = (j+kk)*ROWL+i+k;
                    nn[idx].food = 0.3;
                }
            }
            spacex += bspace;
        }
        spacey += bspace;
    }
}
            

void initfoodtree(Node *nn)
{
    int i,j,nbranch,brspace, idx;

    brspace = 10;
    nbranch = 1;
    for(i=0;i<NROWS-20;i++){
        if(i==0){
            for(j=0;j<ROWL;j++){
                idx = i*ROWL+j;
                nn[idx].food = 0.3;
            }
            continue;
        }
        for(j=0;j<nbranch;j++){
            idx = i*ROWL+ROWL/2+j*brspace;
            nn[idx].food = 0.3;
            idx = i*ROWL+ROWL/2-j*brspace;
            nn[idx].food = 0.3;
        }
        if(i%(2*brspace) == 0){
            for(j=ROWL/2-(nbranch*brspace);j<ROWL/2+(nbranch*brspace);j++){
                idx = i*ROWL+j;
                nn[idx].food = 0.3;
            }
            nbranch++;
        }
        if(nbranch>10)
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


    
