#!/usr/bin/env python3
"""Author flat-frame project marks and homing animations in the OLED format.

Raster tools run only on the asset-authoring machine. The printer shares the
bounded sprite decoder and its existing display timer.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/assets/menu-symbols'
RUNTIME = ROOT/'host/klippy/extras/m300_menu_sprites.json'
NAMES = ('project-klipper', 'project-zortrax', 'homing-xy', 'homing-z', 'homing-all')
FRAME_MS = 500


def frame_svg(name, frame):
    if name not in NAMES or frame not in range(4):
        raise ValueError('Unknown menu symbol/frame')
    x = (12, 21, 30, 21)[frame]
    parts = ['<rect x="4" y="3" width="42" height="44" rx="1"/>',
             '<path d="M4 11h42M8 14v24m34-24v24M8 42h34"/>',
             '<path d="M%d 5v5h6V5m-4 5v3h2v-3"/>' % x]
    if name == 'project-klipper':
        parts += ['<path d="M14 18v20m0-10 20-10M22 24l13 14" stroke-width="2.2"/>']
    elif name == 'project-zortrax':
        parts += ['<path d="M14 19h22L14 38h22M14 23h11m0 11h11" stroke-width="2.2"/>']
    elif name == 'homing-xy':
        parts += ['<path d="M12 24h26m-4-4 4 4-4 4M25 16v16m-4-12 4-4 4 4"/>',
                  '<path d="M12 34l6 6m0-6-6 6m20-6 3 3 3-3m-3 3v3"/>']
    elif name == 'homing-z':
        y = (29, 26, 23, 26)[frame]
        parts += ['<path d="M12 16h10l-10 8h10M32 16v22m-4-17 4-5 4 5"/>',
                  '<path d="M10 %dH26l-3-3H13z"/>' % y]
    elif name == 'homing-all':
        parts += ['<path d="M12 24h26m-4-4 4 4-4 4M25 16v16m-4-12 4-4 4 4"/>',
                  '<path d="M10 34l5 6m0-6-5 6m11-6 3 3 3-3m-3 3v3m9-6h6l-6 6h6"/>',
                  '<circle cx="%d" cy="%d" r="2" fill="white"/>' % ((15,20,30,20)[frame],(21,27,21,19)[frame])]
    parts += ['<path d="M%d 44h3" stroke-width="2"/>' % (12+frame*7)]
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 50 50" color="white">'
            '<rect width="50" height="50" fill="black"/>'
            '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
            +''.join(parts)+'</g></svg>\n')


def main():
    import cairosvg
    from PIL import Image, ImageDraw, ImageFont
    OUT.mkdir(parents=True, exist_ok=True)
    bank = dict(format='M300_ACTIVITY_SPRITES_V1', symbols={})
    images = {}
    for name in NAMES:
        frames, records = [], []
        for index in range(4):
            svg = frame_svg(name, index)
            (OUT/('%s_%d.svg' % (name, index))).write_text(svg)
            png = cairosvg.svg2png(bytestring=svg.encode())
            image = Image.open(io.BytesIO(png)).convert('L').point(lambda p: 255 if p >= 128 else 0)
            frames.append(image)
            values = image.tobytes()
            packed = bytes((values[i] & 0xf0) | (values[i+1] >> 4) for i in range(0,2500,2))
            records.append(dict(sha256=hashlib.sha256(packed).hexdigest(),
                zlib_b64=base64.b64encode(zlib.compress(packed,9)).decode()))
            image.save(OUT/('%s_%d.png' % (name, index)))
        bank['symbols'][name] = dict(width=50,height=50,frame_ms=FRAME_MS,frames=records)
        images[name] = frames
        frames[0].save(OUT/(name+'.gif'),save_all=True,append_images=frames[1:],
                       duration=FRAME_MS,loop=0,disposal=2,optimize=False)
    RUNTIME.write_text(json.dumps(bank,indent=2)+'\n')
    font = ImageFont.truetype('DejaVuSans.ttf',22)
    small = ImageFont.truetype('DejaVuSans.ttf',14)
    sheets = []
    for frame in range(4):
        sheet = Image.new('RGB',(660,390),'#13181d')
        draw = ImageDraw.Draw(sheet)
        draw.text((26,18),'M300 OLED / menu',font=font,fill='white')
        for index,(name,label) in enumerate(zip(NAMES,('Klipper','Zortrax M300'))):
            left = 26+index*320
            draw.rounded_rectangle((left,60,left+290,360),radius=12,fill='#20262c',outline='#3d4952')
            icon = images[name][frame].resize((200,200),Image.Resampling.NEAREST).convert('RGB')
            sheet.paste(icon,(left+45,82))
            draw.text((left+20,298),label,font=font,fill='white')
            draw.text((left+20,333),'50 x 50 / 4 frames / 500 ms',font=small,fill='#aebac4')
        sheets.append(sheet)
    sheets[0].save(OUT/'preview.png')
    sheets[0].save(OUT/'preview.gif',save_all=True,append_images=sheets[1:],
                   duration=FRAME_MS,loop=0,disposal=2,optimize=False)
    homing = []
    for frame in range(4):
        sheet = Image.new('RGB',(980,390),'#13181d')
        draw = ImageDraw.Draw(sheet)
        draw.text((26,18),'M300 OLED / homing',font=font,fill='white')
        for index,(name,label) in enumerate(zip(NAMES[2:],('Homing XY','Homing Z','Homing ALL'))):
            left=26+index*320
            draw.rounded_rectangle((left,60,left+290,360),radius=12,fill='#20262c',outline='#3d4952')
            sheet.paste(images[name][frame].resize((200,200),Image.Resampling.NEAREST).convert('RGB'),(left+45,82))
            draw.text((left+20,298),label,font=font,fill='white')
            draw.text((left+20,333),'50 x 50 / 4 frames / 500 ms',font=small,fill='#aebac4')
        homing.append(sheet)
    homing[0].save(OUT/'homing-preview.png')
    homing[0].save(OUT/'homing-preview.gif',save_all=True,append_images=homing[1:],duration=FRAME_MS,loop=0,disposal=2,optimize=False)
    print('Generated 2 flat-frame menu marks, 3 homing symbols and animated previews')


if __name__ == '__main__':
    main()
