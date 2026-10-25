"""Reject note stems/accidentals when borrowing ordinary-staff barlines."""
import numpy as np


def reliable_staff_barlines(ink,staff,candidates,tab=None):
    lines=staff['lines'];spacing=staff['spacing'];height=lines[-1]-lines[0]+1
    radius=max(5,round(spacing*1.25));core=max(2,round(spacing*.18));accepted=[]
    for x in candidates:
        x=round(x)
        if x<=staff['left']+spacing or x>=staff['right']-spacing:accepted.append(x);continue
        # A continuous line through the inter-staff gap is stronger evidence
        # than a stem that only spans the five-line band.
        if tab is not None and tab['lines'][0]>lines[-1]+spacing:
            gap=ink[lines[-1]+2:tab['lines'][0]-2,max(0,x-core):x+core+1]
            if gap.size and np.mean(np.any(gap>0,axis=1))>=.85:
                accepted.append(x);continue
        left=max(0,x-radius);right=min(ink.shape[1],x+radius+1)
        top=max(0,round(lines[0]-spacing));bottom=min(ink.shape[0],round(lines[-1]+spacing)+1)
        region=ink[top:bottom,left:right].copy()
        for line in lines:
            y=line-top;region[max(0,y-1):min(region.shape[0],y+2),:]=0
        region[:,max(0,x-core-left):min(region.shape[1],x+core+1-left)]=0
        # A barline has no attached note head, beam or second accidental stem.
        if np.count_nonzero(region)<=max(6,round(height*.15)):accepted.append(x)
    return accepted
