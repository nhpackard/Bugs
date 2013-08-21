#!/opt/local/bin/python

# scriptedfun.com Scrolling Background Demo
# http://www.scriptedfun.com/
# December 9, 2006
# MIT License

# 1945.bmp
# taken from the Spritelib by Ari Feldman
# http://www.flyingyogi.com/fun/spritelib.html
# Common Public License

import os, pygame
from pygame.locals import *

# game constants
SCREENRECT = Rect(0, 0, 640, 480)

def imgcolorkey(image, colorkey):
    if colorkey is not None:
        if colorkey is -1:
            colorkey = image.get_at((0, 0))
        image.set_colorkey(colorkey, RLEACCEL)
    return image

def load_image(filename, colorkey = None):
    filename = os.path.join('data', filename)
    image = pygame.image.load(filename).convert()
    return imgcolorkey(image, colorkey)

class SpriteSheet:
    def __init__(self, filename):
        self.sheet = load_image(filename)
    def imgat(self, rect, colorkey = None):
        rect = Rect(rect)
        image = pygame.Surface(rect.size).convert()
        image.blit(self.sheet, (0, 0), rect)
        return imgcolorkey(image, colorkey)
    def imgsat(self, rects, colorkey = None):
        imgs = []
        for rect in rects:
            imgs.append(self.imgat(rect, colorkey))
        return imgs

class Arena:
    speed = 2
    def __init__(self):
        w = SCREENRECT.width
        h = SCREENRECT.height
        self.tileside = self.oceantile.get_height()
        self.counter = 0
        self.ocean = pygame.Surface((w, h + self.tileside)).convert()
        for x in range(w/self.tileside):
            for y in range(h/self.tileside + 1):
                self.ocean.blit(self.oceantile, (x*self.tileside, y*self.tileside))
    def increment(self):
        self.counter = (self.counter - self.speed) % self.tileside
    def decrement(self):
        self.counter = (self.counter + self.speed) % self.tileside

def main():
    pygame.init()

    # set the display mode
    winstyle = 0
    bestdepth = pygame.display.mode_ok(SCREENRECT.size, winstyle, 32)
    screen = pygame.display.set_mode((640, 480+2*32), winstyle, bestdepth)

    # load images, assign to sprite classes
    # (do this before the classes are used, after screen setup)
    spritesheet = SpriteSheet('1945.bmp')

    Arena.oceantile = spritesheet.imgat((268, 367, 32, 32))

    # decorate the game window
    pygame.display.set_caption('scriptedfun.com - press UP, DOWN, ESC, or Q')

    # initialize game groups
    all = pygame.sprite.RenderPlain()

    # initialize our starting sprites
    arena = Arena()

    # to help understand how scrolling works, press ESC
    clip = True

    clock = pygame.time.Clock()

    while 1:

        # get input
        for event in pygame.event.get():
            if event.type == QUIT:
                return
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    screen.fill((0, 0, 0))
                    pygame.display.flip()
                    clip = not clip
                elif event.key == K_q:
                    return

        if pygame.key.get_pressed()[K_UP]:
            arena.decrement()
        if pygame.key.get_pressed()[K_DOWN]:
            arena.increment()

        # update all the sprites
        all.update()

        # draw the scene
        if clip:
            screen.blit(arena.ocean, (0, 0), (0, arena.counter, SCREENRECT.width, SCREENRECT.height))
        else:
            screen.fill((0, 0, 0))
            screen.blit(arena.ocean, (0, arena.tileside-arena.counter))
        all.draw(screen)
        pygame.display.flip()
        clock.tick(30)

if __name__ == '__main__': main()
