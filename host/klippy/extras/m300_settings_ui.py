# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded original-font Settings/Information menu composition, no actions."""
from functools import lru_cache

from .m300_leveling_oem import draw_sprite, draw_text, width


@lru_cache(maxsize=64)
def menu_frame(labels, active, selected, frame_type, sprite=None):
    frame=frame_type()
    if not labels:return frame.wire_bytes()
    selected=max(0,min(int(selected),len(labels)-1))
    visible=(list(range(min(5,len(labels)))) if selected<5 else
             [0]+list(range(selected-3,selected+1)))
    row=visible.index(selected);center=row*12+7
    for y in range(64):
        if abs(y-center)>2:frame.pixel(8,y)
    for dy in range(-2,3):
        frame.pixel(8+(-1 if selected==0 else 1)*(3-abs(dy)),center+dy)
    for row,index in enumerate(visible):
        x=16 if index==0 else 20;y=row*12
        draw_text(frame,x,y,labels[index])
        if index in active:draw_text(frame,x+width(labels[index])+4,y+1,'<')
    if sprite is not None:
        draw_sprite(frame, sprite)
    return frame.wire_bytes()
