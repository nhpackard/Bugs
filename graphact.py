#!/usr/bin/env python


from pygame import *
from math import *
from random import *
import sys
from time import sleep
import collections
import pdb;

argv = sys.argv
if len(argv)>1:
    datfile = argv[1]
    datout = open(datfile,"w")
else:
    datfile = None
    
    
maxact = 4000                            # max number of activity traces in graph...
Width = 300
Height = 200
ymax = 200
ymax = 100000
ncount = 0                          # number of calls to trace

def trace(screen, colvalvec):            # eachcolval = [key,activityvalue]
                                         #        self.traceinit()
    cnt = 0
    cnt1 = 0
    yvals = []
    cols = []
    global ymax
    global ncount
    #        pdb.set_trace()
    for colval in colvalvec:            # separate color from yvals
        cols.append(colval[0])
        yvals.append(colval[1])
        cnt += 1
        if cnt>maxact:
            print "too many activity points..."
            break
    # do the scroll:
    if ncount<Width:      # first, don't scroll
        yvals = [Height - y * Height / ymax
                 for y in yvals]
        cnt1 = 0
        for i in range(len(yvals)):
            x = ncount
            y = yvals[i]
            col = cols[i]
            screen.set_at((x,y),col)
    else:                           # then scroll
        yvals = [Height - y * Height / ymax
                 for y in yvals]
        screen.scroll(-1,0)    # -1 => 1 pixel to left
        draw.line(screen,[100,100,100], # grey line first
                  (Width-1,Height),(Width-1,0))
        for i in range(len(yvals)):
            x = Width-1
            y = yvals[i]
            col = cols[i]
            screen.set_at((x,y),col)
    ncount += 1
    display.update()


import os
from numpy import fromfile
from numpy import sin,pi
from os import system

# set window position
os.environ['SDL_VIDEO_WINDOW_POS'] = "%d,%d" % (20,300)

# rainbow colormap:
norm = lambda x: min(max(int((x+1)*128),0),255)
s = lambda t: sin(2*pi*t)
spec = lambda t: (norm(s(t*0.9+0.2)), norm(s(t*0.9+0.9)), norm(s(t*0.9+0.5)))
palette = tuple(spec(x/256.) for x in range(256))


def omain():
    system("rm -f /tmp/activity; mkfifo -m 666 /tmp/activity")
    pipename = "/tmp/activity"
    print 'opening',pipename
    pipefd = open(pipename,"r")
    print 'opened',pipename
    while True:
        dat = pipefd.readline()
        dat = [int(x) for x in dat.split()]
        print dat
        print '\n---------------\n'

def main():
    global ymax
    system("rm -f /tmp/activity; mkfifo -m 666 /tmp/activity")
    pipename = "/tmp/activity"
    
    print 'opening',pipename
    pipefd = open(pipename,"r")
    print 'opened',pipename
    
    # foo = Graph(0,250,Width,Height,"Activity")
    screen = display.set_mode([Width, Height])
    display.set_caption("Activity")
    draw.rect(screen, [100, 100, 100],(0, 0 , Width, Height + 1), 0)
    display.update()
    actcnt = 0;
    colors = {}
    cnt = 0;
    while True:
        # get input
        for ee in event.get():
            if ee.type == QUIT:
                return
            elif ee.type == KEYDOWN:
                if ee.key == K_ESCAPE:
                    return
                elif ee.key == K_PLUS:
                    ymax = ymax * 2
                    print 'new ymax =',ymax
                elif ee.key == K_KP_PLUS:
                    ymax = ymax * 2
                    print 'new ymax =',ymax
                elif ee.key == K_EQUALS:
                    ymax = ymax * 2
                    print 'new ymax =',ymax
                elif ee.key == K_MINUS:
                    ymax = ymax / 2
                    print 'new ymax =',ymax
        """
        yval = cnt%Height
        col = palette[cnt%255]
        trace(screen,[(col,yval)])
        cnt += 1
        """
        try:
            dat = pipefd.readline()
        except:
            print 'had a problem reading activity pipe.'
        dat = [int(x) for x in dat.split()]
        ldat = len(dat)
        if ldat == 0:
            return
        if ldat % 4:
            print "length of activity output not multiple of 4!"
            print '++++++++++ '
            print dat
            print '---------------\n'
        if datfile != None:            # write to external file
            for dd in dat:
                datout.write(str(dd)+' ')
            datout.write("\n")
        fofo = range(0,ldat,4)          # swizzle data to graph
        dat = [dat[fofo[i]:(fofo[i]+4)] for i in range(len(fofo))]
        dat = [(bin(x)+bin(y)+bin(z),w) for [x,y,z,w] in dat]
        for (xx,act) in dat:
            if xx not in colors:
                if cnt==0:              # 1st data chunk all white
                    colors[xx] = (255,255,255)
                else:
                    colors[xx] = palette[actcnt%255]
                    actcnt += 1
        trdat = [(colors[xx],yy) for xx,yy in dat]
        if len(trdat) > maxact:
            trdat = trdat[0:maxact]
        trace(screen,trdat)
        cnt += 1                        # counting number of data chunks coming from bugs program

if __name__=='__main__':
    main()

