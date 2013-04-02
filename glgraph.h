// glgraph.h

#define CLIP 0		// CLIP 0 runs faster, but can crash if writing off screen...
#define DEFAULTX	640	// default window x size (pixels)
#define DEFAULTY	480	// default window y size (pixels)
#define TXSIZE		32	// fontsize
#define TXFONT		20	// font 0 - system, 1 - finer block, 2 - slightly curly
#define TXMAX		1024	// max label length in pixels...
#define TILERECTF	0	// for exact tiling of rectf() calls...

extern int gl_wind;
extern int gl_pen;
extern int gl_fullscreen;
extern float gl_oxfact,gl_oyfact;
extern float gl_xhold,gl_yhold,gl_zhold;
extern int gl_xsize,gl_ysize;
extern int gl_ix, gl_iy;		// default screen size
extern int gl_left, gl_top;		// default screen position
extern float gl_oleft,gl_oright,gl_obottom,gl_otop,gl_oznear,gl_ozfar;	// ortho() default
extern char	*gl_DBPtr,*gl_DBPtr1,*gl_DBPtr2,*gl_DBmaxPtr,*gl_DBminPtr;
extern unsigned long gl_color;
typedef	struct
			{
			long rowl,nrows,rowbytes;
			char *data;
			}
			gl_Pat;
extern	gl_Pat	gl_DestPat;

extern int gl_keys[512];		// for recording key presses
extern int gl_shift;
extern int gl_ctl;
extern int gl_opt;
extern int gl_count;			// to enable single key presses
extern int gl_print;
extern float gl_delt;			// adjust rate of parameter change
extern int gl_flip;
extern float gl_xpos,gl_ypos,gl_zpos;
extern float gl_xrot,gl_yrot,gl_zrot;
extern float gl_fovy;			// field of view for gluPerspective()
extern float gl_zset;			// z axis camera position
extern float gl_zoom;			// display zoom
extern float gl_amp;
extern long gl_lines;
extern int gl_bwctl;
extern int gl_overlay;
extern long gl_sync;
extern int gl_framecount;
extern int gl_vframerate;				// video frame rate flag
extern int gl_timer;					// timer interval (msec)
extern struct timeval gl_tm,gl_tm1;		// for fps calculations
extern int gl_imx,gl_imy;				// raw mouse coordinates
extern int gl_butnum;					// mouse button number
extern int gl_butstate;					// mouse button state
extern float gl_mousex,gl_mousey;		// scaled mouse coordinates (0, 1)

#define BLACK                   0
#define WHITE                   1
#define RED						2
#define GREEN					3
#define BLUE					4
#define YELLOW					5
#define MAGENTA					6
#define CYAN					7

void initgraph(char *cname);
void prefsize(long ix,long iy);
void prefrez(long ix,long iy);
void prefposition(long ix,long iy);
void g_pendn();
void g_penup();
void g_move(float,float);
void g_move3(float,float,float);
void g_clear();
void g_color(long);
void g_backcolor(long);
void g_RGBcolor(float,float,float);
void g_RGBbackcolor(float,float,float);
void g_setgray(float);
void ReSize(int Width, int Height);

void scale(float xlo,float xhi,float ylo,float yhi);
void wscale(float xlo,float xhi,float ylo,float yhi);
void wind(long ixlo,long ixhi,long iylo, long iyhi);

void clear(void);
void gl_setbuf(char *Buf,long value);
void color(long);
long RGBcolor(float,float,float);
void setrgbcolor(float,float,float);
void setgray(float);
long setcolor(long ir,long ig,long ib);
void bresh(long,long,long,long);

void dotati(long,long);
void gl_scan(long,long,long);
void brcirc(long,long,long);
void brcircf(long,long,long);
void circ( float, float, float);
void circf(float,float,float);
void brellip(long x0,long y0,long a, long b);
void brellipf(long x0,long y0,long a, long b);
void ellipse(float x,float y,float a,float b);
void ellipsef(float x,float y,float a,float b);
void brect(long,long,long,long);
void brectf(long,long,long,long);
void rect(float,float,float,float);
void rectf(float,float,float,float);
void Dotem2d(float *, long);
void BDotem2d(float *, long);
void BDoti(long,long);

void gl_setbuf(char *Buf,long value);
void gl_copybuf(char *,char *);
void gl_copybufr(char *,char *);
void copy(long,long);
void copymask(long,long,unsigned long);
void target(long);

void penup();
void pendn();
void move(float,float);
void movei(long,long);
void dotat(float,float);
void linef(float,float,float,float);

void copyPat(gl_Pat,gl_Pat,long,long);
void copyPata(gl_Pat,gl_Pat,long,long);
void initlabel(void);
void labelsz(long size);
void drawnum(long n,long xpos,long ypos);
void drawnumf(long n,float x,float y);
void label(char *cname,long xpos,long ypos);
void labela(char *cname,long xpos,long ypos);
void labelf(char *cname,float x,float y);
void labelaf(char *cname,float x,float y);
void labelcolor(long value);
void Printf(char *format,...);
void labit(long x,long y);
void labitf(float x, float y);

void keyCB(unsigned char key, int x, int y);
void keyUpCB(unsigned char key, int x, int y);
void specialKeyPressed(int key, int x, int y);
void specialKeyUp(int key, int x, int y);
void clickCB(int button, int state, int x, int y);
void mouseCB(int x, int y);
void updatekeys();
void printhelp();
extern void glutSwapBuffers();
extern void glutPostRedisplay();
//extern void	glutInit((int) (&ac), (char**) av);
extern void glutMainLoop( );

