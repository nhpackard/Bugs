
#include <GLUT/glut.h>
#include <sys/time.h>
#include "glgraph.h"
#include "bugs.h"

struct {
	GLenum		texEnum;
	GLint		texFilter;	
	GLuint		texID;
	GLint		texWidth;
	GLint		texHeight;
} Wnd;

void videoTimer(int n);

int firstex = 0;				// first texture load flag
//extern unsigned short Vout[];	// user space video out plane

void videoInitTexture(int width, int height)
{
	Wnd.texEnum = GL_TEXTURE_RECTANGLE_EXT;
	Wnd.texFilter = GL_LINEAR;
	Wnd.texWidth = width;
	Wnd.texHeight = height;
		
	glEnable(Wnd.texEnum);
	glGenTextures (1, &Wnd.texID);
	glDisable(Wnd.texEnum);
}

void videoNewWindow()				// create texture, video-in destination, start videoTimer()
{
	videoInitTexture(SIZEX, SIZEY);
	glutTimerFunc(0, videoTimer, 123);	// Do the first poll straight away
	gettimeofday(&gl_tm,NULL);
}

void videoDisplay()   
{
float xlo,xhi,ylo=0,yhi=gl_iy;
	
	if(gl_flip) {xhi = 0; xlo = gl_ix; }
	else		{xlo = 0; xhi = gl_ix; }

	glClear (GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

	glMatrixMode(GL_MODELVIEW);
	glLoadIdentity();
	glTranslatef(gl_xpos,gl_ypos,gl_zpos);
	glTranslatef(.5 * gl_ix, .5 * gl_iy, 0);
	glRotatef(gl_yrot, 0, 1, 0);
	glRotatef(gl_xrot, 1, 0, 0);
	glRotatef(gl_zrot, 0, 0, 1);
	glTranslatef(-.5 * gl_ix, -.5 * gl_iy, 0);

	glEnable(Wnd.texEnum);
	
	glColor3f (1.0, 1.0, 1.0); // no coloring
	
	glBegin(GL_QUADS);
		glTexCoord2f(0, 0);
		glVertex2f(xlo, ylo);
		glTexCoord2f(0, Wnd.texHeight);	
		glVertex2f(xlo, yhi);
		glTexCoord2f(Wnd.texWidth, Wnd.texHeight);
		glVertex2f(xhi, yhi);
		glTexCoord2f(Wnd.texWidth, 0);
		glVertex2f(xhi, ylo);
	glEnd();
	
	glDisable(Wnd.texEnum);
}

void videoUpdateFrame(void* pData, long dataSize)
{
	glBindTexture(Wnd.texEnum, Wnd.texID);

	if (!firstex) {		// set parameters, upload the first image
		glTextureRangeAPPLE(Wnd.texEnum, dataSize, pData);  
		glTexParameteri(Wnd.texEnum, GL_TEXTURE_STORAGE_HINT_APPLE , GL_STORAGE_SHARED_APPLE); 
		
		glPixelStorei(GL_UNPACK_CLIENT_STORAGE_APPLE, 1);

		glTexParameteri(Wnd.texEnum, GL_TEXTURE_MIN_FILTER, Wnd.texFilter);
		glTexParameteri(Wnd.texEnum, GL_TEXTURE_MAG_FILTER, Wnd.texFilter);
		glTexParameteri(Wnd.texEnum, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
		glTexParameteri(Wnd.texEnum, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
	
		glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
		glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);			
		
		glTexImage2D(   Wnd.texEnum,		// GLenum target,
						0,					// GLint level,
						GL_RGBA,			// GLint internalformat,
						Wnd.texWidth,		// GLsizei width,
						Wnd.texHeight,		// GLsizei height,
						0,					// GLint border,
						GL_BGRA,
						GL_UNSIGNED_INT_8_8_8_8_REV,
						pData );			//const GLvoid *pixels
		firstex = 1; }
	else {				// upload subsequent images
		glTexSubImage2D(Wnd.texEnum,					// GLenum target,
						0,								// GLint level,
						0,								// GLint xoffset
						0,								// GLint yoffset
						Wnd.texWidth,					// GLsizei width,
						Wnd.texHeight,					// GLsizei height,
						GL_BGRA,
						GL_UNSIGNED_INT_8_8_8_8_REV,
						pData); } 	//const GLvoid *pixels
}

void videoTimer(int n)
{
	glutTimerFunc(gl_timer, videoTimer, 123);
	videoUpdateFrame(Vout, 4*SIZEX*SIZEY);
	Display();				// call our main display program!
	updatekeys();
}
