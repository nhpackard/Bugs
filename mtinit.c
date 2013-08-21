
//  ising simulation initialization routines...

#include <unistd.h>				// for getopt
#include <stdio.h>
#include <math.h>
#include "ising.h"
#include "myrand4.h"

//static short oldepth;

void usage()
{
	fprintf(stderr,"-r  random number seed\n");
	fprintf(stderr,"-t  number of time steps\n");
	fprintf(stderr,"-n  number of transient time steps\n");
	fprintf(stderr,"-m  mutation rate\n");
	fprintf(stderr,"-p  drive period\n");
	fprintf(stderr,"-o  [[print time series]]\n");
}


void mtinit(int ac, const char *av[])
{
	float defectdens,initdens;
	char c;
	_seed=time(0);					// every run random
	nsteps = 10000;

// Tc = 2.269
  Temp = 2.27;
  Hfield = 0.005;
  initdens = 0.5;
  defectdens = 0.0;
  diffrate = 0.00;
  mutrate = 0.00;
  driveper = 20;
  transient = 100;

// end default... now change if option passed.........
  while ((c = getopt(ac, (char **) av, "s:t:n:T:H:d:D:r:m:p:N:o")) != -1) {
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
		case 'T':				// temperature
			Temp = atof(optarg);
			break;
		case 'H':				// H field strength
			Hfield = atof(optarg);
			break;
		case 'd':				// initial density
			initdens = atof(optarg);
			break;
		case 'D':				// defect density
			defectdens = atof(optarg);
		case 'r':				// diffusion rate
			diffrate = atof(optarg);
			break;
		case 'm':				// mutation rate
			mutrate = atof(optarg);
			break;
		case 'p':				// drive period
			driveper = atoi(optarg);
			break;
		case 'N':				// no graphics
			displayctl = 0;
			break;
		case 'o':				// print time series
			tsctl = 1;
			break;
		case '?':
			printf("unknown arg %c\n", optopt);
		case 'h':
			usage();
			exit(0);
		}
  }

//steps_per_data = 10;
// display = 1;
//strcpy(outfile,"sglass.dat");


	printf("\n\nhi there!  \n2-d ising spin glass model \nhit <esc> to exit\n");
	printf("arrow keys change temperature and applied field\n\n");

	printf("Settings:\n");
	printf("Temp = %g\n",Temp);
	Beta = 1.0/Temp;
	printf("beta: %f\n",Beta);
	printf("Hfield = %g\n",Hfield);
	printf("initial_density = %g\n",initdens);
	printf("initial_defect_density = %g\n",defectdens);
	printf("diffusion_rate = %g\n",diffrate);
	printf("mutation_rate = %g\n\n",mutrate);
	printf("drive_period = %ld\n\n",driveper);

// initialize bond arrays	
	rannodes(vlinks,defectdens);
	rannodes(hlinks,defectdens);
// initialize ising array
	rannodes(nodes,initdens);
//	load Boltzmann factor lookup...
	ldboltz();
}

void isexit(void)
{

}

/* Ising model simulation control */

int startopt, regsize, momopt;
float temp, density, sdensity;

void setstart(void)
{
printf("Initial spins options:\n0:zero; 1:random; 2:rand reg; 3:single site; 4:checkers : ");
scanf("%d",&startopt);
//printf("%d\n",startopt);

switch(startopt)
	{
	case 1:
	printf("Enter density (0.5) : ");
	scanf("%f",&density);
	break;

	case 2:
	printf("Enter size of region : ");
	scanf("%d",&regsize);
	printf("Enter density (0.5) : ");
	scanf("%f",&density);
	break;

	case 0:
	case 3:
	case 4:
	break;
	}
}

void mkstart()
{
	int i, j;
	double ftmp;

	setplane(nodes,-1);

	switch(startopt)
	{
		int flag;
	case 1:
	
		srand(TickCount());
		for (i=0;i<ROWL;i++)
			for (j=0;j<NROWS;j++){
				ftmp = f_rand();
				if (ftmp < density) setsite(i,j,1);
			}
		break;

	case 2:
		for (i=ROWL/2-regsize;i<NROWS/2+regsize;i++)
			for (j=ROWL/2-regsize;j<NROWS/2+regsize;j++){
				ftmp = f_rand();
				if (ftmp < density) setsite(i,j,1);
			}
		break;

	case 3:
		setsite(ROWL/2,NROWS/2,1);
		break;
	
	case 4:
		flag = 0;
		for(i=0;i<ROWL;i++)
		{
			for(j=0;j<NROWS;j++)
			{
				if(flag) setsite(i,j,1);
				flag ^= 1;
			}
			flag ^= 1;
		}
		break;
	}

}

void setplane(Node * nn, int val){
	int i;
	for(i=0;i<NMAX;i++)
		nn->occ = val;
}


void setsite(int i,int j, int val)
{
nodes[i+ROWL*j].occ=val;
}


//	load Boltzmann factor lookup...
/*************

Boltz[0:4] are entries for when center spin=0, nbrsum btwn 0 and 4,
nbrsum 0 low energy, 4 high energy
Boltz[5:9] are entries for when center spin=1, nbrsum btwn 0 and 4,
nbrsum 0 high energy, 4 low energy

entries 2,3,4  & 7,6,5
are "definite flip" entries
entries 0,1  & 8,7 
flip w/ Boltzmann probability

 *************/

void ldboltz(void)
{
long i;

Beta = 1.0/Temp;
for(i=0;i<5;i++)
//	Boltz[i] = exp((i-2.0)*4.0*Beta);
	Boltz[i] = exp(((i-2.0)*4.0+2.0*Hfield)*Beta);
for(i=5;i<10;i++)
//	Boltz[i] = exp((7.0-i)*4.0*Beta);
	Boltz[i] = exp(((7.0-i)*4.0-2.0*Hfield)*Beta);

for(i=0;i<10;i++)
	{
	if(Boltz[i]>=1.0)
		iBoltz[i] = 0xffffffff;		// 4294967295 = 0xFFFFFFFF
	else
		iBoltz[i] = Boltz[i]*4294967296.0;
	}
// printf("Boltzman LUT:\n");
// for(i=0;i<10;i++)
// 	printf("%d\t%ld\t\t%g\n",i,iBoltz[i],Boltz[i]);

}
void oldboltz(void)
{
long i;

Beta = 1.0/Temp;
for(i=0;i<5;i++)				//  part of the LUT used if spin is 0
//	Boltz[i] = exp((i-2.0)*4.0*Beta);
	Boltz[i] = exp(((i-2.0)*4.0+2.0*Hfield)*Beta);
for(i=5;i<10;i++)				// part of the LUT used if spin is 1
//	Boltz[i] = exp((7.0-i)*4.0*Beta);
	Boltz[i] = exp(((7.0-i)*4.0-2.0*Hfield)*Beta);

for(i=0;i<10;i++)
	{
	if(Boltz[i]>=1.0)
		iBoltz[i] = 0xffffffff;		// 4294967295 = 0xFFFFFFFF
//		iBoltz[i] = 4294967295u;	// 4294967295 = 0xFFFFFFFF
	else
		iBoltz[i] = Boltz[i]*4294967296.0;
	}

// printf("Boltzman LUT:\n");
// for(i=0;i<10;i++)
// 	printf("%d\t%ld\t\t%g\n",i,iBoltz[i],Boltz[i]);

}
