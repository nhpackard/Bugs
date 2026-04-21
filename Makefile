CC     = gcc
CFLAGS = -O2 -Wall -fPIC

UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
    SHARED_FLAG = -dynamiclib
    LIB         = C/libbugs.dylib
else
    SHARED_FLAG = -shared
    LIB         = C/libbugs.so
endif

.PHONY: all clean

all: $(LIB)

$(LIB): C/bugs.c C/bugs.h
	$(CC) $(CFLAGS) $(SHARED_FLAG) -o $@ C/bugs.c -lm

clean:
	rm -f C/libbugs.so C/libbugs.dylib
