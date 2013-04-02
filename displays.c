#include "bugs.h"
#include "glgraph.h"

#if RES == 0
#define SZ1 1   // for CELLSZ .01
#define SZ2 2
#define SZM1 1
#define SZM2 2
#define YDISP 2
#endif

#if RES == 1
#define SZ1 1   // for CELLSZ .02
#define SZ2 3
#define SZM1 1
#define SZM2 7
#define YDISP 4
#endif

#if RES == 2
#define SZ1 1   // for CELLSZ .04
#define SZ2 7
#define SZM1 1
#define SZM2 15
#define YDISP 8
#endif
#if RES == 3
#define SZ1 2   // for CELLSZ .08
#define SZ2 16
#define SZM1 2
#define SZM2 32
#define YDISP 17
#endif


// draws a bug node, construct color from food
void drawnodebug(long n)
{
float x1,y1,x2,y2;
long ix1,iy1,ix2,iy2,i1,j1,i2,j2;
//long nn;
long n1,n2;
double food;
double bugfood;

n1 = n2 = n;
i1 = n1%ROWL;
j1 = n1/ROWL;
x1 = i1 * CELLSZ - 1.5;
y1 = j1 * CELLSZ - 1.0;
x1 -= gl_oleft;
x1 *= gl_oxfact;
ix1 = x1;
y1 -= gl_otop;
y1 *= gl_oyfact;
iy1 = y1 - YDISP;
i2 = n2%ROWL;
j2 = n2/ROWL;
x2 = i2 * CELLSZ - 1.5;
y2 = j2 * CELLSZ - 1.0;
x2 -= gl_oleft;
x2 *= gl_oxfact;
ix2 = x2;
y2 -= gl_otop;
y2 *= gl_oyfact;
iy2 = y2 - YDISP;

// put together the color...
food = nodes[n].food;
if(nodes[n].bug !=0)
    bugfood = nodes[n].bug->food;
else bugfood = 0;

bugcolor(food,bugfood);

//color(c);
brectf(ix1+SZ1,iy1+SZ1,ix2+SZ2,iy2+SZ2);
//gl_rect(ix1+SZ1,iy1+SZ1,ix1+SZ2,iy1+SZ2);
//gl_rect(ix2+SZ1,iy2+SZ1,ix2+SZ2,iy2+SZ2);
}

//#define NCOL 8
#define NCOL 65536
unsigned long sg_color[NCOL];

void bugcolor_init()
{
    // index into color array will be 2 bytes
    // one byte food
    // second byte bug (e.g. bug food)
    // food green gradient
    // bug blue gradient
    unsigned int i,j,idx;
    double R,G,B;
	
    for(i=0;i<256;i++){
        for(j=0;j<256;j++){
            idx = (i<<8) | j;
            R = j/256.0;
            G = i/128.0;
            B = j/256.0;
            sg_color[idx] = RGBcolor(R,G,B);
        }
    }
}

void bugcolor(double food,double other)
{
    unsigned int idx,ifood,iother;
	static int first=1;
	if(first){
		bugcolor_init();
		first=0;
	}
    food = food > 1 ? 1 : food;
    food = food < 0 ? 0 : food;
    other = other > 1 ? 1 : other;
    other = other < 0 ? 0 : other;
    ifood = food*255;
    iother = other*255;
    idx = (ifood<<8) | iother;
    gl_color = sg_color[idx];
}


void drawnode(long n,long c)
{
float x1,y1,x2,y2;
long ix1,iy1,ix2,iy2,i1,j1,i2,j2;
//long nn;
long n1,n2;

n1 = n2 = n;
i1 = n1%ROWL;
j1 = n1/ROWL;
x1 = i1 * CELLSZ - 1.5;
y1 = j1 * CELLSZ - 1.0;
x1 -= gl_oleft;
x1 *= gl_oxfact;
ix1 = x1;
y1 -= gl_otop;
y1 *= gl_oyfact;
iy1 = y1 - YDISP;
i2 = n2%ROWL;
j2 = n2/ROWL;
x2 = i2 * CELLSZ - 1.5;
y2 = j2 * CELLSZ - 1.0;
x2 -= gl_oleft;
x2 *= gl_oxfact;
ix2 = x2;
y2 -= gl_otop;
y2 *= gl_oyfact;
iy2 = y2 - YDISP;

color(c);

//gl_rect(ix1+SZ1,iy1+SZ1,ix1+SZ2,iy1+SZ2);
//gl_rect(ix2+SZ1,iy2+SZ1,ix2+SZ2,iy2+SZ2);
brectf(ix1+SZ1,iy1+SZ1,ix2+SZ2,iy2+SZ2);
color(BLACK);
brect(ix1+SZ1,iy1+SZ1,ix2+SZ2,iy2+SZ2);
}


// not doing spin glass lattices...
#if 0
void drawnodevh(long n)
{
float x1,y1,x2,y2;
long ix1,iy1,ix2,iy2,i1,j1,i2,j2;
//long nn;
long n1,n2,ss,hh,vv;

n1 = n2 = n;
i1 = n1%ROWL;
j1 = n1/ROWL;
x1 = i1 * CELLSZ - 1.5;
y1 = j1 * CELLSZ - 1.0;
x1 -= gl_oleft;
x1 *= gl_oxfact;
ix1 = x1;
y1 -= gl_otop;
y1 *= gl_oyfact;
iy1 = y1 - YDISP;
i2 = n2%ROWL;
j2 = n2/ROWL;
x2 = i2 * CELLSZ - 1.5;
y2 = j2 * CELLSZ - 1.0;
x2 -= gl_oleft;
x2 *= gl_oxfact;
ix2 = x2;
y2 -= gl_otop;
y2 *= gl_oyfact;
iy2 = y2 - YDISP;
ss = nodes[n].occ;
hh = hlinks[n].occ;
vv = vlinks[n].occ;
sgcolor(ss,hh,vv);

//gl_rect(ix1+SZ1,iy1+SZ1,ix1+SZ2,iy1+SZ2);
//gl_rect(ix2+SZ1,iy2+SZ1,ix2+SZ2,iy2+SZ2);
brectf(ix1+SZ1,iy1+SZ1,ix2+SZ2,iy2+SZ2);
//color(BLACK);
//recti(ix1+SZ1,iy1+SZ1,ix2+SZ2,iy2+SZ2);
}
#endif

void border()
{
color(BLACK);
 move(1.5,1.0);
pendn();
move(1.5,-1.0);
move(-1.5,-1.0);
move(-1.5,1.0);
move(1.5,1.0);
penup();
}

// display bugs
void display()
{
    long i;
    color(WHITE);
    clear();
	for(i=0; i<NMAX; i++)
		drawnodebug(i);

//		if(nodes[i].occ>0)
//			drawnode(i,0);		// 0 = black
//    border();
//    drawnum(nsteps,520,35);
//    Printf("\nT = %.4lf",Temp);
//    labit(280,480);
//    Printf("\nh = %.4lf",Hfield);
//    labit(20,480);
//    border();
//	drawbuffer();
}


// prints iteration rate, ll is number of ticks...
void printhz(long nstps,long ll)
{
float hz;

hz = 60.0 * (float)nstps / (float)ll;
drawnum(hz,520,35);
label(" Hz     ",-1,-1);
//drawbuffer();
}

// no spin glass stuff...
#if 0
unsigned long sg_color[8];
void sgcolor_init()
{
	sg_color[0] = 0x0;
	sg_color[1] = RGBcolor(0.7,0.0,0.0);
	sg_color[2] = RGBcolor(0.0,0.0,0.7);
	sg_color[3] = RGBcolor(0.0,0.7,0.0);
	sg_color[4] = RGBcolor(0.99,0.99,0.99);
	sg_color[5] = RGBcolor(0.99,0.6,0.6);
	sg_color[6] = RGBcolor(0.6,0.6,0.99);
	sg_color[7] = RGBcolor(0.6,0.99,0.6);
//	int i;
//	for(i=0;i<8;i++)
//		fprintf(stderr,"%x\n",sg_color[i]);
}

void sgcolor(long spin,long h,long v)
{
	if(spin==-1 && h==1 && v==1) gl_color=sg_color[0];
	if(spin==-1 && h==-1 && v==1) gl_color=sg_color[1];
	if(spin==-1 && h==1 && v==-1) gl_color=sg_color[2];
	if(spin==-1 && h==-1 && v==-1) gl_color=sg_color[3];
	if(spin==1 && h==1 && v==1) gl_color=sg_color[4];
	if(spin==1 && h==-1 && v==1) gl_color=sg_color[5];
	if(spin==1 && h==1 && v==-1) gl_color=sg_color[6];
	if(spin==1 && h==-1 && v==-1) gl_color=sg_color[7];
}
#endif

	
void tst_color()
{
	int i,x,y;
    color(WHITE);
    clear();
	for(i=0;i<8;i++){
		x = i*20;
		y = i*20;
		gl_color=sg_color[i];
		brectf(x,y,x+20,y+20);
	}
//	drawbuffer();
}

		
