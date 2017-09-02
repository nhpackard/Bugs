#!/usr/bin/env python


from pygame import *
from math import *
from random import *
import sys
from time import sleep
import collections

argv = sys.argv
if len(argv)>1:
    datfile = argv[1]
    print 'outputting pop data to',datfile
    datout = open(datfile,"w")
else:
    datfile = None


WIN_W = 300
WIN_H = 200
class Graph :
    def __init__ (self, posx, posy, Width, Height, legend):        
        # pygame init
        self.screen = display.set_mode([WIN_W, WIN_H])
        display.set_caption(legend)
        font.init()
        # x position of the point
        self.xpos = 0
        # size of graph
        self.posx = posx
        self.posy = posy
        self.Width = Width
        self.Height = Height
        self.legend = legend
        self.ymax = 1100
        self.firstime = 1
        # ring buffer
        self.ring = collections.deque(maxlen=self.Width)
        self.ncount = 0
        self.traceinit()


    def traceinit(self):
        # background
        draw.rect(self.screen, [100, 100, 100],
                  (self.posx, self.posy , self.Width, self.Height + 1), 0)
        # x-axis
        #draw.line(self.screen, [0, 0, 0], 
        #         (self.posx, self.posy + self.Height/2), 
        #  (self.posx + self.Width, self.posy + self.Height/2))
        # legend
        f = font.SysFont("Times New Roman", 13)
        self.legend = 'Max = '+str(self.ymax)
        s = f.render(self.legend, False, (0, 0, 0))
        self.screen.blit(s, (self.posx+10, self.posy+10))
        self.refresh()
        # setup
        if self.firstime:
            self.firstime=0
            y=self.ymax/2.0
            self.coord = [self.posx + self.xpos, 
                          self.posy + y * self.Height / self.ymax]
            self.last = self.coord

    def trace(self, y):
        self.ring.append(y)
        # rescale:
        if self.ymax<y:
            self.ymax = 1.3*y
        # scale the y vals:
        self.pts = [(i,self.ring[i]) for i in range(len(self.ring))]
        self.pts = [(self.posx+x,
                     self.posy + self.Height - y * self.Height / self.ymax)
                     for x,y in self.pts]
        # self.coord = [self.posx + self.xpos, 
        #                             self.posy + self.Height - y * self.Height / self.ymax]
        # do the scroll:
        # if self.ncount<self.Width:
        #     self.pts = [(x,y) for (x,y) in self.ring]
        # else:
        #     self.pts = [(x-self.ncount+self.Width,y) for (x,y) in self.ring]
        self.traceinit()
        if len(self.pts)> 2:
            draw.aalines(self.screen, [255, 255, 255], False, self.pts)
        self.ncount += 1
        # increment the xpos
        self.xpos = (self.xpos + 1)
        # remember
        self.last = self.coord
        
    def refresh (self):
        display.update()
        
'''
import argparse
import os
'''
        
import os
from numpy import fromfile
from numpy import sin
from os import system


def main():
    system("rm -f /tmp/population; mkfifo -m 666 /tmp/population")
    pipename = "/tmp/population"
    print 'opening',pipename
    pipefd = open(pipename,"r")
    print 'opened',pipename
    
    foo = Graph(0,0,WIN_W,WIN_H,"population")
    foo.trace(100.0)
    foo.refresh()
    cnt = 0;
    while True:
        # get input
        for ee in event.get():
            if ee.type == QUIT:
                return
            elif ee.type == KEYDOWN:
                if ee.key == K_ESCAPE:
                    return
                #        try:
        try:
            dat = float(pipefd.readline())
        except:
            return
            # dat = fromfile(pipefd,float,1,sep=' ')
            #            dat = 500.0*sin(cnt/8.0)
            #            print dat
        foo.trace(dat)
        foo.refresh()
        if datfile != None:
            datout.write(str(dat)+'\n')
        cnt += 1
            #        except:
            #return
        
if __name__=='__main__':
    main()
