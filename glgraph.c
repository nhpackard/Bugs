// rushdiag version...
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <sys/time.h>
#include <OpenGL/OpenGL.h>	// for CG stuff
#include <GLUT/glut.h>
#include <unistd.h>			// sleep()
#include <Carbon/Carbon.h>	// for Delay(), ExitToShell()
//#include <QuickTime/QuickTime.h>
#include "glgraph.h"
//#include "rstuff.h"
#include "bugs.h"

#if 0						// defined in Carbon.h
struct Rect {
   short    top;
   short    left;
   short    bottom;
   short    right;
};
typedef struct Rect Rect;

// does the same as above, except that "Rect" not entered in the structure namespace
typedef struct {
   short    top;
   short    left;
   short    bottom;
   short    right;
} Rect;
#endif

int gl_wind;
int gl_pen = 0;
int gl_fullscreen = 0;
float gl_xhold,gl_yhold,gl_zhold;
//#define DEFAULTX 640
//#define DEFAULTY 640
int gl_xsize=640,gl_ysize=480;		// default screen size
int gl_ix = 640, gl_iy = 480;		// default texture size
int gl_left = 320, gl_top = 54;		// default screen position

long	gl_scrnsize,gl_mode,gl_dbl,gl_BPL,gl_SPL;
float	gl_oleft=0,gl_oright=1,gl_obottom=0,gl_otop=1,gl_oznear= -1,gl_ozfar=1;	// ortho() default
float	gl_oxfact,gl_oyfact;
long	gl_ixhold,gl_iyhold;
char	*gl_DBPtr,*gl_DBPtr1=0,*gl_DBPtr2=0,*gl_DBmaxPtr,*gl_DBminPtr;
long	gl_ixminclip,gl_ixmaxclip,gl_iyminclip,gl_iymaxclip;
long	gl_iwx1,gl_iwx2,gl_iwy1,gl_iwy2;
unsigned long gl_color;
//struct	gl_Pat
//	{
//	long rowl,nrows,rowbytes;
//	char *data;
//	};
gl_Pat gl_DestPat;	// either the screen or an off-screen buffer

int gl_keys[512];					// for recording key presses
int gl_shift = 0;
int gl_ctl = 0;
int gl_opt = 0;
int gl_count = 10;					// to enable single key presses
int gl_print  = 0;
float gl_delt = 1;					// adjust rate of parameter change
int gl_flip = 0;					// mirror reversal flag
float gl_xpos=0,gl_ypos=0,gl_zpos=0;
float gl_xrot=0,gl_yrot=0,gl_zrot=0;
float gl_fovy=60;					// field of view for gluPerspective()
float gl_zset;						// z axis camera position
float gl_zoom = 1;					// display zoom
float gl_amp = -80;
long gl_lines = 79;
int gl_bwctl = 1;
int gl_overlay = 0;
long gl_sync = 0;
int gl_framecount = 0;
int gl_vframerate = 0;				// video frame rate flag
int gl_timer = 0;					// timer interval (msec)
struct timeval gl_tm,gl_tm1;		// for fps calculations
int gl_imx,gl_imy;					// raw mouse coordinates
int gl_butnum;						// mouse button number
int gl_butstate;					// mouse button state
float gl_mousex,gl_mousey;			// scaled mouse coordinates (0, 1)
void printhelp();
typedef struct tagVideoWindow VideoWindow;
VideoWindow* videoNewWindow();
extern int firstex;
extern Rect vidRect;
extern void videoDisplay();
extern void initvid(int,int);
//extern unsigned short Vout[SIZEX * SIZEY];
extern void *Vptr;

void initgraph(char *cname)
{
float theta,pi = 3.1416;

printhelp();

//initvid(SIZEX, SIZEY);	// initialize digitizer
//initvid(352,288);		// acceptable isight resolution setting
//initvid(0, 0);		// sets vidRect to maximum available from digitizer
//gl_ix = vidRect.right; gl_iy = vidRect.bottom;	// default is 640 x 480

glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA);
glutInitWindowSize(gl_xsize, gl_ysize);
glutInitWindowPosition(gl_left, gl_top);
gl_wind = glutCreateWindow(cname);

glMatrixMode(GL_PROJECTION);
glLoadIdentity();
gluPerspective(gl_fovy, (float)gl_ix/(float)gl_iy, .1f, 10000.0f);
glScalef(1,-1,1);
theta = (gl_fovy / 360.0) * pi;				// half angle
gl_zset = (.5 * gl_iy) / tan(theta);
gl_zset *= gl_zoom;
glTranslatef(-gl_ix/2, -gl_iy/2 , -gl_zset);	// window scaled to (gl_ix, gl_iy)

glShadeModel(GL_FLAT);					
glClearColor(0.0f, 0.0f, 0.0f, 1.0f);		// black window background
	
glutDisplayFunc (videoDisplay);
//glutIdleFunc(videoDisplay);

glutSetCursor(GLUT_CURSOR_NONE);
glutSetKeyRepeat(GLUT_KEY_REPEAT_OFF);
//glutReshapeFunc(ReSize);
glutKeyboardFunc(keyCB);
glutKeyboardUpFunc(keyUpCB);
glutSpecialFunc(&specialKeyPressed);
glutSpecialUpFunc(&specialKeyUp);
glutMouseFunc (clickCB);
glutMotionFunc (mouseCB);
//glutPassiveMotionFunc (mouseCB);

videoNewWindow();		// create texture, video-in destination, start video

// set graphics target here, 0 to malloc memory locally
gl_DBPtr1 = (char *)Vout;		// user array
//gl_DBPtr1 = (char *)Vptr;		// gworld memory
//gl_DBPtr1 = 0;				// malloc

gl_BPL = 4 * gl_ix;		// 4 bytes per pixel!  (for this version)
gl_SPL = gl_BPL/4;

target(1);				// set gl_DBPtr to gl_DBPtr1

gl_ixminclip = 0;
gl_ixmaxclip = gl_ix-1;
gl_iyminclip = 0;
gl_iymaxclip = gl_iy-1;

gl_DestPat.rowl = gl_ix;
gl_DestPat.nrows = gl_iy;
gl_DestPat.rowbytes = gl_BPL;
gl_DestPat.data = gl_DBPtr;

scale(0,1,0,1);		// default scaling
wind(0,gl_ix-1,0,gl_iy-1);
}

void prefsize(long ix,long iy)		// display window size
{
gl_xsize = ix;
gl_ysize = iy;
gl_ix=ix;
gl_iy=iy;
}

void prefrez(long ix,long iy)		// texture size (call after above)
{
gl_ix=ix;
gl_iy=iy;
//gl_zoom = gl_ix/gl_xsize;
}

void prefposition(long ix,long iy)
{
gl_left=ix;
gl_top=iy;
}

void g_pendn()
{
if(!gl_pen)
	{
	glBegin(GL_LINE_STRIP);
	glVertex3f(gl_xhold,gl_yhold,gl_zhold);
	}
gl_pen = 1;
}

void g_penup()
{
glEnd();
gl_pen = 0;
}
	
void g_move(float x, float y)
{
if(gl_pen)
	glVertex2f(x,y);
gl_xhold = x;
gl_yhold = y;
}

void g_move3(float x, float y, float z)
{
if(gl_pen)
	glVertex3f(x,y,z);
gl_xhold = x;
gl_yhold = y;
gl_zhold = z;
}

void g_clear()
{
glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
}

void g_color(long value)
{
switch(value)
	{
	case BLACK:
		glColor3f(0,0,0);
		break;
	case WHITE:
		glColor3f(1,1,1);
		break;
	case RED:
		glColor3f(1,0,0);
		break;
	case GREEN:
		glColor3f(0,1,0);
		break;
	case BLUE:
		glColor3f(0,0,1);
		break;
	case YELLOW:
		glColor3f(1,1,0);
		break;
	case MAGENTA:
		glColor3f(1,0,1);
		break;
	case CYAN:
		glColor3f(0,1,1);
		break;
	}
}

void g_backcolor(long value)
{
switch(value)
	{
	case BLACK:
		glClearColor(0,0,0,0);
		break;
	case WHITE:
		glClearColor(1,1,1,0);
		break;
	case RED:
		glClearColor(1,0,0,0);
		break;
	case GREEN:
		glClearColor(0,1,0,0);
		break;
	case BLUE:
		glClearColor(0,0,1,0);
		break;
	case YELLOW:
		glClearColor(1,1,0,0);
		break;
	case MAGENTA:
		glClearColor(1,0,1,0);
		break;
	case CYAN:
		glClearColor(1,0,1,0);
		break;
	}
}

void g_RGBcolor(float r,float g,float b)
{
glColor3f(r,g,b);
}

void g_RGBbackcolor(float r,float g,float b)
{
glClearColor(r,g,b,0);
}

void g_setgray(float a)
{
glColor3f(a,a,a);
}

void ReSize(int Width, int Height)
{
gl_xsize = Width;
gl_ysize = Height;
glViewport(0, 0, Width, Height);
printf("wwidth %d  height %d\n",Width,Height);
//glMatrixMode(GL_PROJECTION);
//glLoadIdentity();
//glOrtho(gl_oleft, gl_oright, gl_obottom, gl_otop, gl_oznear, gl_ozfar);
//Display();
//printf("%d %d\n",gl_xsize,gl_ysize);
}

// original routines...

// scale into full screen
void scale(float xlo,float xhi,float ylo,float yhi)
{
float rr,ll,tt,bb,ixhi,ixlo,iyhi,iylo;

gl_oleft=xlo; gl_oright=xhi;
gl_obottom=ylo; gl_otop=yhi;

rr = gl_oright; ll = gl_oleft; tt = gl_otop; bb = gl_obottom;
//ixhi = gl_screenRect.right - 1; ixlo = gl_screenRect.left;	// adjust for
//iyhi = gl_screenRect.bottom - 1; iylo = gl_screenRect.top;	// mac coordinates
ixhi = gl_ix-1; ixlo = 0;		// adjust for mac coordinates??
iyhi = gl_iy-1; iylo = 0;		// (this seems to give exact pixel fits)
gl_oxfact = (ixhi-ixlo)/(rr-ll);
gl_oyfact = (iyhi-iylo)/(bb-tt);
}

// scale into window set by wind()
void wscale(float xlo,float xhi,float ylo,float yhi)
{
float ixhi,ixlo,iyhi,iylo;

ixhi = gl_iwx2; ixlo = gl_iwx1;		// get window coords
iyhi = gl_iwy2; iylo = gl_iwy1;		// set by wind()
gl_oxfact = (ixhi-ixlo)/(xhi-xlo);
gl_oyfact = (iyhi-iylo)/(ylo-yhi);	// flip to video coords here
gl_oleft = xlo - gl_iwx1/gl_oxfact;
gl_oright = xhi - gl_iwx1/gl_oxfact;
gl_otop  = yhi - gl_iwy1/gl_oyfact;
gl_obottom = ylo - gl_iwy1/gl_oyfact;
}

// in video coordinates
void wind(long ixlo,long ixhi,long iylo, long iyhi)
{
gl_iwx1 = ixlo;
gl_iwx2 = ixhi;
gl_iwy1 = iylo;
gl_iwy2 = iyhi;
}

/* 32 */
void color(long value)
{
unsigned long lval=0;
switch(value)
	{
	case BLACK:
		lval = 0x00000000;
		break;
	case WHITE:
		lval = 0x00ffffff;
		break;
	case RED:
		lval = 0x00ff0000;
		break;
	case GREEN:
		lval = 0x0000ff00;
		break;
	case BLUE:
		lval = 0x000000ff;
		break;
	case YELLOW:
		lval = 0x00ffff00;	// R + G
		break;
	case MAGENTA:
		lval = 0x00ff00ff;	// R + B
		break;
	case CYAN:
		lval = 0x0000ffff;	// B + G
		break;
	default:
		lval = value;
		break;
	}
gl_color = lval;
}

/* 32 */
long RGBcolor(float r,float g,float b)
{
long ir,ig,ib;

ir = 256 * r;
if(ir == 256) ir = 255;
ig = 256 * g;
if(ig == 256) ig = 255;
ib = 256 * b;
if(ib == 256) ib = 255;
ir &= 255;
ig &= 255;
ib &= 255;
gl_color = ir<<16 | ig<<8 | ib;
return(gl_color);
}

/* 32 */
void setrgbcolor(float r,float g,float b)
{
gl_color = RGBcolor(r,g,b);
}

/* 32 */
void setgray(float a)
{
gl_color = RGBcolor(a,a,a);
}

/* 32 */
long setcolor(long ir,long ig,long ib)
{
#if 0
if(ir >= 256) ir = 255;
if(ir < 0) ir = 0;
if(ig >= 256) ig = 255;
if(ig < 0) ig = 0;
if(ib >= 256) ib = 255;
if(ib < 0) ib = 0;
#endif
ir &= 255;
ig &= 255;
ib &= 255;
gl_color = ir<<16 | ig<<8 | ib;
return(gl_color);
}

void clear(void)
{
	gl_setbuf(gl_DBPtr,gl_color);
}

/*  32  */
//#define macro_dotati(x,y) *(gl_DBPtr + y*gl_BPL + x) = gl_color
#if CLIP
#define macro_dotati(x,y) dotati(x,y)
#else
#define macro_dotati(x,y) *((long*)gl_DBPtr + y*gl_SPL + x) = gl_color
#endif
//#define macro_dotati(x,y) dotati(x,y)

/* bresenham line-drawing algorithm */
void bresh(long x1,long y1,long x2,long y2)
{
long dx,dy,d,ink1,ink2,x,y,oct;

if(x1>x2)
        {
        x=x1;x1=x2;x2=x;
        y=y1;y1=y2;y2=y;
        }
dx = x2 - x1;
dy = y2 - y1;
x = x1; y = y1;
macro_dotati(x,y);

/* octant dispatch table... */

if(y2>y1)
        {
        if(dx>dy)
                oct=1;
        else
                oct=2;
        }
else
        {
        if(dx>-dy)
                oct=3;
        else
                oct=4;
        }

switch(oct){

case(1):
d = (dy<<1) - dx;
ink1 = (dy<<1);
ink2 = ((dy-dx)<<1);
while(x<x2)
         {
         ++x;
         if(d <= 0 )
                 d += ink1;
         else
                 {
                 d += ink2;
                 ++y;
                 }
         macro_dotati(x,y);
         }
break;

case(3):
d = (-dy<<1) - dx;
ink1 = (-dy<<1);
ink2 = ((-dy-dx)<<1);
while(x<x2)
         {
         ++x;
         if(d <= 0 )
                 d += ink1;
         else
                 {
                 d += ink2;
                 --y;
                 }
         macro_dotati(x,y);
         }
break;

case(2):
d = (dx<<1) - dy;
ink1 = (dx<<1);
ink2 = ((dx-dy)<<1);
while(y<y2)
         {
         ++y;
         if(d <= 0 )
                 d += ink1;
         else
                 {
                 d += ink2;
                 ++x;
                 }
         macro_dotati(x,y);
         }
break;

case(4):
d = (dx<<1) + dy;
ink1 = (dx<<1);
ink2 = ((dx+dy)<<1);
while(y>y2)
         {
         --y;
         if(d <= 0 )
                 d += ink1;
         else
                 {
                 d += ink2;
                 ++x;
                 }
         macro_dotati(x,y);
         }
}
}

void dotati(long x,long y)
{
register long *lPtr;

if(x<gl_ixminclip)return;
if(x>gl_ixmaxclip)return;
if(y<gl_iyminclip)return;
if(y>gl_iymaxclip)return;
lPtr = (long *)gl_DBPtr + y*gl_SPL + x;
#if CLIP
if((lPtr>=(long*)gl_DBminPtr)&&(lPtr<(long*)gl_DBmaxPtr))
#endif
	*lPtr = gl_color;
}

/*  32  */
void gl_scan(long x1,long x2,long y)		// horizontal line-fill routine...
											//  fills x1 to x2 inclusive
{
register long *Ptr1,*Ptr2;

if(y<gl_iyminclip)return;
if(y>gl_iymaxclip)return;
if(x2<gl_ixminclip)return;
if(x1>gl_ixmaxclip)return;
if(x2-x1 < 0) return;
if(x1<gl_ixminclip) x1 = gl_ixminclip;
if(x2>gl_ixmaxclip) x2 = gl_ixmaxclip;

Ptr1 = (long *)gl_DBPtr + y*gl_SPL + x1;
Ptr2 = (long *)gl_DBPtr + y*gl_SPL + x2;

while(Ptr1 <= Ptr2)	// whole-word writes
	*Ptr1++ = gl_color;
}

/* bresenham circle drawing routine */
/*  ..see foley and van dam, pg 87  */

#define dfn dotati
#define cpts(x, y)\
dfn(x+x0,y+y0);dfn(y+x0,x+y0);dfn(-x+x0,y+y0);dfn(y+x0,-x+y0);\
dfn(x+x0,-y+y0);dfn(-y+x0,x+y0);dfn(-x+x0,-y+y0);dfn(-y+x0,-x+y0)

void brcirc(long x0,long y0,long rad)
{
long x,y,d,ink1,ink2;

x=0;
y=rad;
d=1-rad;
ink1=3;
ink2=5-(rad<<1);
cpts(x,y);

while(y>x)
        {
        ++x;
        ink1+=2;
        if(d<0)
        		{
        		d+=ink1;
                ink2+=2;
                }
        else
                {
                d+=ink2;
                ink2+=4;
                --y;
                }
        cpts(x,y);
        }
}

/* bresenham filled circle drawing routine */

void brcircf(long x0,long y0,long rad)
{
long x,y,d,ink1,ink2;

x=0;
y=rad;
d=1-rad;
ink1=3;
ink2=5-(rad<<1);

while(y>x)
        {
        ink1+=2;
        if(d<0)
        		{
        		d+=ink1;
                ink2+=2;

                }
        else
                {
                d+=ink2;
                ink2+=4;
                gl_scan(x0-x,x0+x,y0+y);
                gl_scan(x0-x,x0+x,y0-y);
                --y;
                }
        gl_scan(x0-y,x0+y,y0-x);
        gl_scan(x0-y,x0+y,y0+x);
        ++x;
        }
gl_scan(x0-x,x0+x,y0+y);
gl_scan(x0-x,x0+x,y0-y);
}

void circ(float x,float y,float rad)		// floating point circle routine, radius in x-scaled units...
//float x,y,rad;
{
long ix,iy,irad;

x -= gl_oleft;
x *= gl_oxfact;
ix=x;
y -= gl_otop;
y *= gl_oyfact;
iy=y;
rad *= gl_oxfact;
irad=rad;
brcirc(ix,iy,irad);
//printf("x %f   y %f\n",x,y);
//printf("ix %d   iy %d\n",ix,iy);
}

void circf(float x,float y,float rad)	// floating point filled circle routine, radius in x-scaled units...
{
long ix,iy,irad;

x -= gl_oleft;
x *= gl_oxfact;
ix=x;
y -= gl_otop;
y *= gl_oyfact;
iy=y;
rad *= gl_oxfact;
irad=rad;
brcircf(ix,iy,irad);
}

/* bresenham ellipse drawing routine */
/*  ..see foley and van dam, pg 90  */

#define epts(x, y)\
dfn(x+x0,y+y0);dfn(-x+x0,y+y0);dfn(x+x0,-y+y0);dfn(-x+x0,-y+y0)

void brellip(long x0,long y0,long a, long b)
{
long x,y;
double d1,d2;

x=0;
y=b;
d1 = b*b - a*a*b + .25*a*a;
epts(x,y);

while(a*a*(y-.5) > b*b*(x+1))
	{
	if(d1 < 0)
		d1 += b*b*(2*x+3);
	else
		{
		d1 += b*b*(2*x+3) + a*a*(-2*y+2);
		y--;
		}
	x++;
	epts(x,y);
	}
	
d2 = b*b*(x+.5)*(x+.5) + a*a*(y-1)*(y-1) - a*a*b*b;
while(y > 0)
	{
	if(d2 < 0)
		{
		d2 += b*b*(2*x+2) + a*a*(-2*y+3);
		x++;
		}
	else
		d2 += a*a*(-2*y+3);
	y--;
	epts(x,y);
	}
}

/* bresenham ellipse drawing routine */

void brellipf(long x0,long y0,long a, long b)
{
long x,y;
double d1,d2;

x=0;
y=b;
d1 = b*b - a*a*b + .25*a*a;
//epts(x,y);

while(a*a*(y-.5) > b*b*(x+1))
	{
	if(d1 < 0)
		d1 += b*b*(2*x+3);
	else
		{
		d1 += b*b*(2*x+3) + a*a*(-2*y+2);
		y--;
		}
	x++;
	gl_scan(x0-x,x0+x,y0-y);
	gl_scan(x0-x,x0+x,y0+y);
	//epts(x,y);
	}
	
d2 = b*b*(x+.5)*(x+.5) + a*a*(y-1)*(y-1) - a*a*b*b;
while(y > 0)
	{
	if(d2 < 0)
		{
		d2 += b*b*(2*x+2) + a*a*(-2*y+3);
		x++;
		}
	else
		d2 += a*a*(-2*y+3);
	y--;
	gl_scan(x0-x,x0+x,y0-y);
	gl_scan(x0-x,x0+x,y0+y);
	//epts(x,y);
	}
}

void ellipse(float x,float y,float a,float b)		// floating point ellipse routine
{
long ix,iy,ia,ib;

x -= gl_oleft;
x *= gl_oxfact;
ix=x;
y -= gl_otop;
y *= gl_oyfact;
iy=y;
a *= gl_oxfact;
b *= gl_oyfact;
ia=a; ib= -b;
brellip(ix,iy,ia,ib);
}

void ellipsef(float x,float y,float a,float b)	// floating point filled ellipse routine
{
long ix,iy,ia,ib;

x -= gl_oleft;
x *= gl_oxfact;
ix=x;
y -= gl_otop;
y *= gl_oyfact;
iy=y;
a *= gl_oxfact;
b *= gl_oyfact;
ia=a; ib= -b;
brellipf(ix,iy,ia,ib);
}

void brect(long ix1,long iy1,long ix2,long iy2)		// pixel units rectangle drawing routine
{
gl_scan(ix1,ix2,iy1);
gl_scan(ix1,ix2,iy2);
bresh(ix2,iy1,ix2,iy2);
bresh(ix1,iy1,ix1,iy2);
}

void brectf(long x1,long y1,long x2,long y2)
{
while(y1<=y2)
	{
	gl_scan(x1,x2,y1);
	++y1;
	}
}

void rect(float x1,float y1,float x2,float y2)		// floating point rectangle drawing routine
{
long ix1,iy1,ix2,iy2,ihold;

x1 -= gl_oleft;
x1 *= gl_oxfact;
ix1=x1;
y1 -= gl_otop;
y1 *= gl_oyfact;
iy1=y1;
x2 -= gl_oleft;
x2 *= gl_oxfact;
ix2=x2;
y2 -= gl_otop;
y2 *= gl_oyfact;
iy2=y2;
if(ix1>ix2) {ihold=ix1;ix1=ix2;ix2=ihold;}

gl_scan(ix1,ix2,iy1);
gl_scan(ix1,ix2,iy2);
bresh(ix2,iy1,ix2,iy2);
bresh(ix1,iy1,ix1,iy2);
//printf("%d %d %d %d\n",ix1,iy1,ix2,iy2);
}

void rectf(float x1,float y1,float x2,float y2)		// floating point rectangle fill routine
//float x1,y1,x2,y2;
{
long ix1,iy1,ix2,iy2,ihold;

x1 -= gl_oleft;
x1 *= gl_oxfact;
ix1=x1;
y1 -= gl_otop;
y1 *= gl_oyfact;
iy1=y1;
x2 -= gl_oleft;
x2 *= gl_oxfact;
ix2=x2;
y2 -= gl_otop;
y2 *= gl_oyfact;
iy2=y2;

if(ix1>ix2) {ihold=ix1;ix1=ix2;ix2=ihold;}
if(iy1>iy2) {ihold=iy1;iy1=iy2;iy2=ihold;}
#if TILERECTF
--ix2; --iy2;
#endif
//printf("%d %d %d %d wha?\n",ix1,iy1,ix2,iy2);
while(iy1<=iy2)
	{
	gl_scan(ix1,ix2,iy1);
	++iy1;
	}
}

/* set buffer to given long value... */
/* assumes gl_ix by gl_iy size */

/*  32  */
void gl_setbuf(char *Buf,long value)
{
register unsigned long i,icnt,lval;
unsigned long L[2];
register double *Bptr,fval;

lval = value;					// make 2 copies
L[0] = lval; L[1] = lval;
fval = *((double *)L);

//icnt = (gl_ix*gl_iy)>>2;		// 4 shorts to a double
icnt = (gl_BPL*gl_iy)>>3;		// 8 bytes to a double
//printf("gl_BPL %d\n",gl_BPL);

Bptr = (double*)Buf;
		
for(i=0;i<icnt;i++)
	{
	*Bptr = fval;
	++Bptr;
	}
}

/* copy one buffer to another... */
/* assumes both are gl_ix by gl_iy size */

/*  32  */
void gl_copybuf(char *Buf1,char *Buf2)
{
register unsigned long i,icnt;
register double *Bptr1,*Bptr2;

//icnt = (gl_ix*gl_iy)>>2;		// 4 shorts to a double
icnt = (gl_BPL*gl_iy)>>3;		// 8 bytes to a double

Bptr1 = (double*)Buf1;
Bptr2 = (double*)Buf2;
		
for(i=0;i<icnt;i++)
	{
	*Bptr2++ = *Bptr1++;
	}
}

/* copy one buffer to another, with mirror reversal */
/* assumes both are gl_ix by gl_iy size */

/*  32  */
void gl_copybufr(char *Buf1,char *Buf2)
{
register unsigned long i,j;
register long *Bptr1,*Bptr2;

Bptr2 = (long*)Buf2;
		
for(i=0;i<gl_iy;i++)
	{
	Bptr1 = (long*)Buf1;
	Bptr1 += (i+1) * (gl_BPL>>2) - 1;
	for(j=0;j< (gl_BPL>>2) ;j++)
		*Bptr2++ = *Bptr1--;
	}
}

/* copy via buffer number, at the moment */
/* we're implementing just two buffers... */

void copy(long srcnum,long dstnum)
{
char *Buf1=0,*Buf2=0;

if(srcnum == 1) 
	Buf1 = gl_DBPtr1;
if(srcnum == 2) 
	Buf1 = gl_DBPtr2;
if(dstnum == 1) 
	Buf2 = gl_DBPtr1;
if(dstnum == 2) 
	Buf2 = gl_DBPtr2;

gl_copybuf(Buf1,Buf2);
}

/* copy via buffer number, with a mask.  pixels	from		*/
/* the source which are equal to the mask aren't copied.	*/
/* at the moment we're implementing just two buffers		*/
void copymask(long srcnum,long dstnum,unsigned long mask)
{
register unsigned long i,icnt,val;
register unsigned long *Bptr1=0,*Bptr2=0;

if(srcnum == 1) 
	Bptr1 = (unsigned long*)gl_DBPtr1;
if(srcnum == 2) 
	Bptr1 = (unsigned long*)gl_DBPtr2;
if(dstnum == 1) 
	Bptr2 = (unsigned long*)gl_DBPtr1;
if(dstnum == 2) 
	Bptr2 = (unsigned long*)gl_DBPtr2;

icnt = (gl_BPL*gl_iy)>>2;		// 4 bytes to a long
		
for(i=0;i<icnt;i++)
	{
	val = *Bptr1++;
	if(val != mask)
		*Bptr2 = val;
	Bptr2++;
	}
}

/* sets "target", the destination of drawing calls */
/* 1 - background #1, 2 - background #2  */
void target(long bufnum)
{
if(bufnum == 1)
	gl_DBPtr = gl_DBPtr1;
if(bufnum == 2)
	gl_DBPtr = gl_DBPtr2;

if(gl_DBPtr == NULL)
	{
	long n;
	n = gl_BPL * gl_iy;
	gl_DBPtr = malloc(n);
	if(gl_DBPtr == NULL)
		{
		printf("trouble with target %ld malloc...\n",bufnum);
		sleep(5);
		ExitToShell();
		}
	else
		printf("malloced %ld bytes for buffer %ld\n",n,bufnum);
	}

gl_DBminPtr = gl_DBPtr;
gl_DBmaxPtr = gl_DBPtr + gl_BPL*gl_iy;
gl_DestPat.data = gl_DBPtr;

if(bufnum == 1)				// in case we malloced up a new buffer
	gl_DBPtr1 = gl_DBPtr;
if(bufnum == 2)
	gl_DBPtr2 = gl_DBPtr;
}

/*  Dotem2d(Dptr,ndots) - takes an array of ndots 2d dots and writes them  */
/*                        to the current drawing buffer (gl_DBPtr)  */
/*  if clipping commented out, may well crash if dots outside scaled region...  */

/*  32  */
void Dotem2d(float *Dptr, long ndots)
{
long i;
float *lDptr;
register float x,y;
register long ix,iy;
register long *lPtr;

lDptr = Dptr;

for(i=0;i<ndots;i++)
	{
	x = *lDptr++;
	if(x<gl_oleft){++lDptr;continue;}
	if(x>gl_oright){++lDptr;continue;}
	x -= gl_oleft;
	x *= gl_oxfact;
	ix = x;
	
	y = *lDptr++;
	if(y>gl_otop)continue;
	if(y<gl_obottom)continue;
	y -= gl_otop;
	y *= gl_oyfact;
	iy = y;
	
	lPtr = (long *)gl_DBPtr + iy*gl_SPL + ix;
#if CLIP
	if((lPtr>=(long*)gl_DBminPtr)&&(lPtr<(long*)gl_DBmaxPtr))
#endif
		*lPtr = gl_color;
	}
}

/*  BDotem2d(Dptr,ndots) - takes an array of ndots 2d dots and writes them  */
/*                        to the current drawing buffer (gl_DBPtr)  */
/*		this version writes a 4 pixel block, referenced to the upper-left pixel  */
/*  if clipping commented out, may well crash if dots outside scaled region...  */

void BDotem2d(float *Dptr, long ndots)
{
long i;
float *lDptr;
register float x,y;
register long ix,iy;
register long *lPtr;

lDptr = Dptr;

for(i=0;i<ndots;i++)
	{
	x = *lDptr++;
	if(x<gl_oleft){++lDptr;continue;}
	if(x>gl_oright){++lDptr;continue;}
	x -= gl_oleft;
	x *= gl_oxfact;
	ix = x;
	
	y = *lDptr++;
	if(y>gl_otop)continue;
	if(y<gl_obottom)continue;
	y -= gl_otop;
	y *= gl_oyfact;
	iy = y;
	
//	if((ix+1) > gl_windRect.right) continue;
//	if((iy+1) > gl_windRect.bottom) continue;
	if((ix+1) > gl_ixmaxclip) continue;
	if((iy+1) > gl_iymaxclip) continue;


	lPtr = (long *)gl_DBPtr + iy*gl_SPL + ix;
#if CLIP
	if((lPtr>=(long*)gl_DBminPtr)&&(lPtr<(long*)gl_DBmaxPtr))
		{
#endif
		*lPtr++ = gl_color;
		*lPtr = gl_color;
		lPtr = (long *)gl_DBPtr + (iy+1)*gl_SPL + ix;
		*lPtr++ = gl_color;
		*lPtr = gl_color;
#if CLIP
		}
#endif
	}
}

/* 2 x 2 dot */

void BDoti(long ix,long iy)
{
dotati(ix,iy);
dotati(ix+1,iy);
dotati(ix,iy+1);
dotati(ix+1,iy+1);
}

/*  *graph-type calls, penup(), pendn(), move(x,y), dotat(x,y)...  */
void penup()
{
gl_pen = 0;
}

void pendn()
{
gl_pen = 1;
}

void move(float x, float y)
{
 register long ix,iy;
 
	x -= gl_oleft;
	x *= gl_oxfact;
	ix = x;
	y -= gl_otop;
	y *= gl_oyfact;
	iy = y;
	
	if(gl_pen)
		bresh(gl_ixhold,gl_iyhold,ix,iy);
	gl_ixhold = ix;
	gl_iyhold = iy;
}

void movei(long ix, long iy)
{
	if(gl_pen)
		bresh(gl_ixhold,gl_iyhold,ix,iy);
	gl_ixhold = ix;
	gl_iyhold = iy;
}

void dotat(float x, float y)
{
 register long ix,iy;
 
	x -= gl_oleft;
	x *= gl_oxfact;
	ix = x;
	y -= gl_otop;
	y *= gl_oyfact;
	iy = y;

	dotati(ix,iy);
}

void linef(float x1, float y1, float x2, float y2)
{
 register long ix1,iy1,ix2,iy2;
 
	x1 -= gl_oleft;
	x1 *= gl_oxfact;
	ix1 = x1;
	y1 -= gl_otop;
	y1 *= gl_oyfact;
	iy1 = y1;
	x2 -= gl_oleft;
	x2 *= gl_oxfact;
	ix2 = x2;
	y2 -= gl_otop;
	y2 *= gl_oyfact;
	iy2 = y2;

	bresh(ix1,iy1,ix2,iy2);
}

/*  copyPat(P,Dest,xoff,yoff) - copies patch P into patch Dest, with offsets.  */
/*                              hopefully clipping P to within Dest...         */
/*								copies patch over if pixel not equal to zero.  */
/*  32  */
void copyPat(gl_Pat P,gl_Pat Dest,long xoff,long yoff)
{
long i,j,nrows,rowl,xjump1,xjump2;
long *Ptr1,*Ptr2,l;

Ptr1 = (long*)P.data; Ptr2 = (long*)Dest.data;
rowl = P.rowl; nrows = P.nrows;
//#if CLIP
if(xoff<0)
	{
	rowl = P.rowl + xoff;
	if(rowl < 0) return;
	Ptr1 -= xoff;
	xoff = 0;	// for setting Ptr2...
	}
if((xoff+P.rowl)>Dest.rowl)
	{
	rowl = Dest.rowl - xoff;
	if(rowl < 0) return;
	}
if(yoff<0)
	{
	nrows = P.nrows + yoff;
	if(nrows < 0) return;
	Ptr1 += (P.nrows - nrows) * (P.rowbytes>>2);
	yoff = 0;
	}
if((yoff+P.nrows)>Dest.nrows)
	{
	nrows = Dest.nrows - yoff;
	if(nrows < 0) return;
	}
//#endif
Ptr2 += yoff*(Dest.rowbytes>>2)  + xoff;

xjump1 = (P.rowbytes>>2)   - rowl;
xjump2 = (Dest.rowbytes>>2)  - rowl;

for(j=0;j<nrows;j++)
        {
        for(i=0;i<rowl;i++)
                {
                l = *Ptr1;
                if(l != 0)
                        *Ptr2 = l;
                ++Ptr1; ++Ptr2;
                }
        Ptr1 += xjump1; Ptr2 += xjump2;
        }
}

/*  copyPata(P,Dest,xoff,yoff) - copies patch P into patch Dest, with offsets.  */
/*                              hopefully clipping P to within Dest...         */
/*								same as copyPat(), except zero pixels copies over also...  */
/*  32  */
void copyPata(gl_Pat P,gl_Pat Dest,long xoff,long yoff)
{
long i,j,nrows,rowl,xjump1,xjump2;
long *Ptr1,*Ptr2;

Ptr1 = (long*)P.data; Ptr2 = (long*)Dest.data;
rowl = P.rowl; nrows = P.nrows;
//#if CLIP
if(xoff<0)
	{
	rowl = P.rowl + xoff;
	if(rowl < 0) return;
	Ptr1 -= xoff;
	xoff = 0;	// for setting Ptr2...
	}
if((xoff+P.rowl)>Dest.rowl)
	{
	rowl = Dest.rowl - xoff;
	if(rowl < 0) return;
	}
if(yoff<0)
	{
	nrows = P.nrows + yoff;
	if(nrows < 0) return;
	Ptr1 += (P.nrows - nrows) * (P.rowbytes>>2);
	yoff = 0;
	}
if((yoff+P.nrows)>Dest.nrows)
	{
	nrows = Dest.nrows - yoff;
	if(nrows < 0) return;
	}
//#endif
Ptr2 += yoff*(Dest.rowbytes>>2)  + xoff;

xjump1 = (P.rowbytes>>2)   - rowl;
xjump2 = (Dest.rowbytes>>2)  - rowl;

for(j=0;j<nrows;j++)
        {
        for(i=0;i<rowl;i++)
                {
                *Ptr2 = *Ptr1;
                ++Ptr1; ++Ptr2;
                }
        Ptr1 += xjump1; Ptr2 += xjump2;
        }
}

/*  copyPatb(P,Dest,xoff,yoff) - extract from patch Dest into patch P, with offsets.  */
/*                              hopefully clipping P to within Dest...         */
/*								reverse copy of copyPata()		*/
/*  32  */
void copyPatb(gl_Pat P,gl_Pat Dest,long xoff,long yoff)
{
long i,j,nrows,rowl,xjump1,xjump2;
long *Ptr1,*Ptr2;

Ptr1 = (long*)P.data; Ptr2 = (long*)Dest.data;
rowl = P.rowl; nrows = P.nrows;
//#if CLIP
if(xoff<0)
	{
	rowl = P.rowl + xoff;
	if(rowl < 0) return;
	Ptr1 -= xoff;
	xoff = 0;	// for setting Ptr2...
	}
if((xoff+P.rowl)>Dest.rowl)
	{
	rowl = Dest.rowl - xoff;
	if(rowl < 0) return;
	}
if(yoff<0)
	{
	nrows = P.nrows + yoff;
	if(nrows < 0) return;
	Ptr1 += (P.nrows - nrows) * (P.rowbytes>>2);
	yoff = 0;
	}
if((yoff+P.nrows)>Dest.nrows)
	{
	nrows = Dest.nrows - yoff;
	if(nrows < 0) return;
	}
//#endif
Ptr2 += yoff*(Dest.rowbytes>>2)  + xoff;

xjump1 = (P.rowbytes>>2)   - rowl;
xjump2 = (Dest.rowbytes>>2)  - rowl;

for(j=0;j<nrows;j++)
        {
        for(i=0;i<rowl;i++)
                {
                *Ptr1 = *Ptr2;
                ++Ptr1; ++Ptr2;
                }
        Ptr1 += xjump1; Ptr2 += xjump2;
        }
}

CGrafPtr		screenCGP;			// reset this stuff after label buffer is used
GDHandle		screenGDH;			// or SetDepth() crashes screen...
static long		initlabelflag = 0;	// so that initlabel() isn't called twice...

Rect				labelR1;
GWorldPtr			labelGW;
gl_Pat				labelPat;
long				labelLength = 0;
long				labelTXSIZE = TXSIZE;
static long			labelX = 0,labelY = 0;
static long			labelVDisp;		// vertical font displacement...
char				labelStr[256];
RGBColor			labelColor = {0,0,65535};	// default label color...
RGBColor			labelBack = {0xffff,0xffff,0xffff};	// default label background color...
RGBColor			labelClr;
RGBColor			qdblack = {0,0,0}, qdyellow = {0xffff,0xffff,0x0000};
RGBColor			qdmagenta = {0xffff,0x0000,0xffff}, qdred = {0xffff,0x0000,0x0000};
RGBColor			qdcyan = {0x0000,0xffff,0xffff}, qdgreen = {0x0000,0xffff,0x0000};
RGBColor			qdblue = {0x0000,0x0000,0xffff}, qdwhite = {0xffff,0xffff,0xffff};

void initlabel()
{
//long n;
PixMapHandle pmh;
FontInfo theFont;

if(!initlabelflag)
	{
	TextSize(labelTXSIZE);
	TextFont(TXFONT);
	//TextFace(bold);
	GetFontInfo(&theFont);
	/* this is a guess for the vertical displacement which seems to work  */
	labelVDisp = theFont.descent - theFont.leading;
	GetGWorld(&screenCGP,&screenGDH);
	SetRect(&labelR1, 0, 0, TXMAX, TXSIZE+theFont.leading);
	/*	Make the offscreen buffer for the labels...	*/
	NewGWorld (&labelGW, 0, &labelR1, nil, nil, 0);
//	QTNewGWorld (&labelGW, k422YpCbCr8CodecType, &labelR1, nil, nil, 0);
//	QTNewGWorld (&labelGW, k32ARGBPixelFormat, &labelR1, nil, nil, 0);	// backwards colors
//	QTNewGWorld (&labelGW, k32BGRAPixelFormat, &labelR1, nil, nil, 0);
	SetGWorld (labelGW, nil);
	TextSize(labelTXSIZE);
	TextFont(TXFONT);
	//TextFace(bold);
	RGBForeColor(&labelColor);
	RGBBackColor(&labelBack);
//	n = (*labelGW).device;
//	pmh = (*labelGW).portPixMap;
	pmh = GetPortPixMap(labelGW);
	LockPixels(pmh);
	labelPat.rowbytes = (**pmh).rowBytes;
	labelPat.rowbytes &= 0x7fff;
	labelPat.data = GetPixBaseAddr(pmh);
	labelPat.nrows = labelTXSIZE+theFont.leading;
	EraseRect(&labelR1);
	initlabelflag = 1;
//	printf("initlabel!\n");
	}
}

// change label size, can only reduce from original TXSIZE
void labelsz(long size)
{
FontInfo theFont;

if(size == labelTXSIZE) return;
if(size > TXSIZE) size = TXSIZE;
labelTXSIZE = size;
TextSize(size);
GetFontInfo(&theFont);
/* this is a guess for the vertical displacement which seems to work  */
labelVDisp = theFont.descent - theFont.leading;
labelPat.nrows = labelTXSIZE+theFont.leading;
SetRect(&labelR1, 0, 0, TXMAX, size+theFont.leading);
EraseRect(&labelR1);
}

// draw number string to label buffer, copy to active buffer...
// if xpos is -1, add to pre-existing stuff in label buffer.
void drawnum(long n,long xpos,long ypos)
{
unsigned char theString[255];

if(!initlabelflag)
	initlabel();

if(xpos != -1)
	{
	EraseRect(&labelR1);
	MoveTo(0,labelTXSIZE-labelVDisp);
	labelLength = 0;
	labelX = xpos;
	labelY = ypos;
	}
	
NumToString(n,theString);
DrawString(theString);
labelLength += StringWidth(theString);
labelPat.rowl = labelLength;
copyPata(labelPat,gl_DestPat,labelX,labelY-labelTXSIZE);
}

// had to write this as calling c2pstr twice on same string
// gives scrambled results
#include <string.h>
const unsigned char *myCtoP(char *str);
const unsigned char *myCtoP(char *str)
{
long i,n;

n = strlen(str);
labelStr[0] = n;
for(i=0;i<n;i++)
	labelStr[i+1] = str[i];
return (const unsigned char *)labelStr;
}

// draws the string str to the label buffer,
// copies to active buffer at (xpos,ypos).
// if xpos is -1, add to pre-existing stuff in label buffer.
void label(char *cname,long xpos,long ypos)
{
const unsigned char *txt;

if(!initlabelflag)
	initlabel();

txt = myCtoP(cname);
if(xpos != -1)
	{
	EraseRect(&labelR1);
	MoveTo(0,labelTXSIZE-labelVDisp);
	labelLength = 0;
	labelX = xpos;
	labelY = ypos;
	}

DrawString(txt);
labelLength += StringWidth(txt);
labelPat.rowl = labelLength;
copyPata(labelPat,gl_DestPat,labelX,labelY-labelTXSIZE);
}

void labela(char *cname,long xpos,long ypos)
{
const unsigned char *txt;

if(!initlabelflag)
	initlabel();

txt = myCtoP(cname);
labelLength = StringWidth(txt);
labelPat.rowl = labelLength;
labelX = xpos;
labelY = ypos;

copyPatb(labelPat,gl_DestPat,labelX,labelY-labelTXSIZE);
MoveTo(0,labelTXSIZE-labelVDisp);
DrawString(txt);
copyPata(labelPat,gl_DestPat,labelX,labelY-labelTXSIZE);
}
// version of label() that accepts position in scaled units.
// if x and y are -1111.0, add to pre-existing stuff in label buffer.
void labelf(char *cname,float x,float y)
{
register long ix,iy;
 
x -= gl_oleft;
x *= gl_oxfact;
ix = x;
y -= gl_otop;
y *= gl_oyfact;
iy = y;
if((x == -1111.0) && (y == -1111.0))
	ix = -1;
label(cname,ix,iy);
}

// version of labela() that accepts position in scaled units.
void labelaf(char *cname,float x,float y)
{
register long ix,iy;
 
x -= gl_oleft;
x *= gl_oxfact;
ix = x;
y -= gl_otop;
y *= gl_oyfact;
iy = y;
labela(cname,ix,iy);
}

// version of drawnum() that accepts position in scaled units.
// if x and y are -1111.0, add to pre-existing stuff in label buffer.
void drawnumf(long n,float x,float y)
{
register long ix,iy;
 
x -= gl_oleft;
x *= gl_oxfact;
ix = x;
y -= gl_otop;
y *= gl_oyfact;
iy = y;
if((x == -1111.0) && (y == -1111.0))
	ix = -1;
drawnum(n,ix,iy);
}

void labelcolor(long value)
{
RGBColor newcol;

if(!initlabelflag) initlabel();

switch(value)
	{
	case BLACK:
		RGBForeColor(&qdblack);
		break;
	case WHITE:
		RGBForeColor(&qdwhite);
		break;
	case RED:
		RGBForeColor(&qdred);
		break;
	case GREEN:
		RGBForeColor(&qdgreen);
		break;
	case BLUE:
		RGBForeColor(&qdblue);
		break;
	case YELLOW:
		RGBForeColor(&qdyellow);
		break;
	case MAGENTA:
		RGBForeColor(&qdmagenta);
		break;
	case CYAN:
		RGBForeColor(&qdcyan);
		break;
	default:
		newcol.red = (value & 0x00ff0000) >> 8;
		newcol.green = (value & 0x0000ff00);
		newcol.blue = (value & 0x000000ff) << 8;
		RGBForeColor(&newcol);
		break;
	}
}

// set label background color
void labelback(long value)
{
RGBColor newcol;

if(!initlabelflag) initlabel();

switch(value)
	{
	case BLACK:
		RGBBackColor(&qdblack);
		break;
	case WHITE:
		RGBBackColor(&qdwhite);
		break;
	case RED:
		RGBBackColor(&qdred);
		break;
	case GREEN:
		RGBBackColor(&qdgreen);
		break;
	case BLUE:
		RGBBackColor(&qdblue);
		break;
	case YELLOW:
		RGBBackColor(&qdyellow);
		break;
	case MAGENTA:
		RGBBackColor(&qdmagenta);
		break;
	case CYAN:
		RGBBackColor(&qdcyan);
		break;
	default:
		newcol.red = (value & 0x00ff0000) >> 8;
		newcol.green = (value & 0x0000ff00);
		newcol.blue = (value & 0x000000ff) << 8;
		RGBBackColor(&newcol);
		break;
	}
}

// prints formatted string into the label buffer
// use like printf(), except precede strings with \n
// to clear the buffer...
#include <stdarg.h>
void Printf(char *format,...)
	{
	char c,Cbuf[128],Cbuf1[128];
	int i,j;
	va_list args;
	const unsigned char *txt;

	if(!initlabelflag)
		initlabel();

	va_start(args,format);
	vsprintf(Cbuf,format,args);
	
	i=j=0;
	while((c = Cbuf[i++]) != '\0')
		{
		if(c == '\n')
			{
			EraseRect(&labelR1);
			MoveTo(0,labelTXSIZE-labelVDisp);
			labelLength = 0;
			}
		else if(c == '\r')
			{
			MoveTo(0,labelTXSIZE-labelVDisp);
			labelLength = 0;
			}
		else
			{
			Cbuf1[j] = c;
			++j;
			}
		}
	Cbuf1[j] = '\0';
	//DrawString(c2pstr(Cbuf1));
	txt = myCtoP(Cbuf1);
	DrawString(txt);
	labelLength += StringWidth(txt);

	}

// write label buffer to desired position on screen.
void labit(long xpos,long ypos)
{
labelX = xpos;
labelY = ypos;
labelPat.rowl = labelLength;
copyPata(labelPat,gl_DestPat,labelX,labelY-labelTXSIZE);
}

// write label buffer to desired position on screen,
// scaled units.
void labitf(float x, float y)
{
register long ix,iy;
 
x -= gl_oleft;
x *= gl_oxfact;
ix = x;
y -= gl_otop;
y *= gl_oyfact;
iy = y;
labit(ix,iy);
}
