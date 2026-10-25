"""Whole-page masking, preserving page geometry and retained pixels."""
import numpy as np
from PIL import ImageDraw

MASK_VERSION='whole_page_gap_v3'

def create_mask(original,staffs,kind):
    staffs=sorted(staffs,key=lambda s:s['lines'][0])
    pixels=np.asarray(original)
    cuts=[0]
    for a,b in zip(staffs,staffs[1:]):
        lo,hi=a['lines'][-1],b['lines'][0]
        # A conservative central gap avoids retaining TAB slurs above its lines.
        # Ambiguous markings between staves require subsequent visual review.
        start=round(lo+(hi-lo)*.35);stop=round(lo+(hi-lo)*.65);mid=(lo+hi)/2
        if stop<=start:raise ValueError('Insufficient gap for whole-page mask')
        ink=(pixels[start:stop].min(axis=2)<160).sum(axis=1)
        cuts.append(min(range(start,stop),key=lambda y:(int(ink[y-start]),abs(y-mid))))
    cuts.append(original.height)
    masked=original.copy();draw=ImageDraw.Draw(masked)
    erased=np.zeros(original.height,dtype=bool);rectangles=[]
    for i,staff in enumerate(staffs):
        if staff['kind']==kind:continue
        y1,y2=cuts[i:i+2]
        draw.rectangle((0,y1,original.width-1,y2-1),fill='white')
        erased[y1:y2]=True;rectangles.append([0,y1,original.width,y2])
    output=np.asarray(masked)
    assert np.array_equal(output[~erased],pixels[~erased])
    assert np.all(output[erased]==255)
    return masked,{'version':MASK_VERSION,'same_size':True,'retained_pixels_identical':True,
                   'erased_pixels_white':True,'rectangles':rectangles}

