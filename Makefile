
# makefile
# fill TG in with program you want to compile
# for gdb use  % make DBG=-g


# swver := $(shell sw_vers | grep ProductVersion | cut -f 2)
TG = bugs

DBG = -O0 -g
ARCH = -arch i386


#CFLAGS = $(DBG) $(ARCH) -Wmost -Wno-deprecated-declarations -g -DHASH_DEBUG=1
CFLAGS = $(DBG) $(ARCH) -Wmost -Wno-deprecated-declarations -g
LIBS = -framework OpenGL -framework GLUT -framework Carbon $(ARCH)
OBJ = $(TG).o glgraph.o vWindow.o displays.o kbd.o uthash.o bugsutil.o bugsinit.o

$(TG):	$(OBJ)
	cc -o $(TG) $(OBJ) $(LIBS)

HEADERS = glgraph.h bugs.h
$(OBJ): $(HEADERS)

clean:
	rm *.o $(TG)

tar:
	tar czvf $(TG).tgz Makefile *.c *.h *.py
