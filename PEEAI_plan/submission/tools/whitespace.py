"""Measure empty space on rendered pages. For each PNG, the near-white share, the share per tenth
of the height and width, and the largest all-near-white rectangle as a fraction of the page
(rect_frac) with its place in percent (x, y, w, h). Used for the deck, the poster and their
figures.

    python3 tools/whitespace.py render/s-01.png render/s-02.png
"""
import sys, glob, json
from PIL import Image
import numpy as np
def largest_rect(mask):
    # mask True = empty; largest all-True axis-aligned rectangle via histogram method
    h,w = mask.shape; heights = np.zeros(w,dtype=int); best=(0,0,0,0,0)
    for r in range(h):
        heights = np.where(mask[r], heights+1, 0)
        stack=[]  # indices
        for c in range(w+1):
            cur = heights[c] if c<w else 0
            start=c
            while stack and stack[-1][1] > cur:
                s,hh = stack.pop()
                area = hh*(c-s)
                if area>best[0]: best=(area,r-hh+1,s,hh,c-s)
                start=s
            stack.append((start,cur))
    return best
res=[]
for f in sys.argv[1:]:
    im = Image.open(f).convert('L'); W0,H0 = im.size
    scale = 200.0/max(W0,H0)
    a = np.asarray(im).astype(int)
    white = a >= 245
    # tenths: 10 horizontal bands (rows) and 10 vertical bands (cols), plus 10x10 grid
    rows = [white[int(i*H0/10):int((i+1)*H0/10)].mean() for i in range(10)]
    cols = [white[:,int(i*W0/10):int((i+1)*W0/10)].mean() for i in range(10)]
    # downsample mask for rectangle search: a cell empty only if fully near-white
    sm = Image.fromarray((~white).astype(np.uint8)*255).resize((max(1,int(W0*scale)),max(1,int(H0*scale))), Image.BOX)
    m = np.asarray(sm) == 0
    area,r0,c0,hh,ww = largest_rect(m)
    frac = area/m.size
    res.append(dict(file=f.split('/')[-1], white=round(white.mean(),3), rows=[round(x,2) for x in rows], cols=[round(x,2) for x in cols],
        rect_frac=round(frac,3), rect_xywh_pct=[round(100*c0/m.shape[1]),round(100*r0/m.shape[0]),round(100*ww/m.shape[1]),round(100*hh/m.shape[0])]))
print(json.dumps(res))
