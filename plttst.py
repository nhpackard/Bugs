
from random import gauss

class delay:
    # Pure time delay of a time sequence, like a tape loop
    def __init__(self, steps):
        # initialize a new delaying object - argument is number of steps
        self.hist = []
        for i in range(steps):
            self.hist.append(0.0)
    def lag(self, input):
        #  Object.lag(input) returns an earlier value of input.
        self.hist.append(input)
        return(self.hist.pop(0))

class generate:
    def __init__(self):
        self.X = 10.0
        self.Y = 10.0
        self.A = -0.2
        self.B = -0.15
        self.C = +0.12
                
    def next(self):
        dX = self.A*self.X + self.B*self.Y + gauss(0.0, .05)
        dY = .4*self.X + self.C*self.Y
        self.X = self.X + dX
        self.Y = self.Y + dY
        return(self.X, self.Y)

    def modA(self, cont, oldcont):
        self.A = self.A * (100 + cont - oldcont)/98.0
    def modB(self, cont, oldcont):
        self.B = self.B * (100 + cont - oldcont)/98.0
    def modC(self, cont, oldcont):
        self.C = self.C * (100 + cont - oldcont)/98.0

# Continuous plotting & control of a dynamic model
# by Mitchell Timin, 1999

# These are Python standard items:
from Tkinter import *
from time import sleep
from thread import start_new_thread, exit

# This is the dynamic model:
from model import generate
model = generate()

# This section sets up the graphics display and controls:
wide = 810 ; high = 560 # pixel dimensions of canvas
Halt = 0
def halt():
    # used by PAUSE button to toggle Halt variable
    global Halt
    if(Halt):
        Halt = 0
    else:
        Halt = 1
    root=Tk()
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    frame = Frame(root)
    frame.pack()
    button = Button(frame, text="QUIT", fg="red", command=frame.quit)
    button.pack(side=LEFT)
    butt = Button(frame, text="PAUSE", fg="blue", command=halt)
    butt.pack(side=LEFT)
    but = Button(frame, text="RESTART", fg="green", command=model.__init__)
    but.pack(side=LEFT)
    scale = Scale(root)
    scale.pack(side=LEFT)
    scal = Scale(root)
    scal.pack(side=LEFT)
    sca = Scale(root)
    sca.pack(side=LEFT)
    canvas=Canvas(root,width=wide,height=high)
    canvas.pack()

# A sequence of short line segments will be drawn on the canvas.
# This code gets ready for that:
offset = 5 # just a few pixels away from the edge
dx = 20 # stepsize in horizontal direction
stime = .15 # real time delay between segments (seconds)

# Y and Z are the model's dependent variables, unscaled.
# ypix and zpix are the scale values in pixels.
# xpix represents time, in pixels horizontally.
yscale = zscale = 10.0
def nexpix(x):
    # returns a tuple of the pixel values representing the models output
    Y, Z = model.next()
    ypix = int((high/2)-Y*yscale)
    zpix = int((high/2)-Z*zscale)
    return x+dx, ypix, zpix

# compute the starting points:
xs, ys, zs = nexpix(offset-dx)

def draw(stime):
    # Repeatedly draws line segments, calling the model for values:
    global xs,ys,zs,dx
# get the user control values:
    pc1, pc2, pc3 = scale.get(), scal.get(), sca.get()
    while 1:
        sleep(stime)
    while(Halt):
        sleep(.1)
# get the user control values:
        c1, c2, c3 = scale.get(), scal.get(), sca.get()
        if(c1 != pc1):
            model.modA(c1, pc1)
        pc1 = c1
    if(c2 != pc2):
        model.modB(c2, pc2)
    pc2 = c2
    if(c3 != pc3):
        model.modC(c3, pc3)
    pc3= c3
#update the model, then draw a line segment for each variable:
    xf, yf, zf = nexpix(xs)
    l1 = canvas.create_line(xs, ys, xf, yf, width=2,fill="blue")
    l2 = canvas.create_line(xs, zs, xf, zf, width=2,fill="green")
# save the endpoints; they will become the starting points:
    xs,ys,zs = xf, yf, zf
# This is to delete the older, offscreen, line segments:
    if l1 > 100 and l2 > 100:
        canvas.delete(l1-100);canvas.delete(l2-100)
    if xs >= wide:
        canvas.move(ALL,-dx,0)
        xs = xs - dx

start_new_thread(draw,(stime,))

root.mainloop()
