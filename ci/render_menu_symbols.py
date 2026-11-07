#!/usr/bin/env python3
"""Author two monochrome project marks with the existing OLED sprite format.

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
NAMES = ('project-klipper', 'project-zortrax')
FRAME_MS = 500


def frame_svg(name, frame):
    if name not in NAMES or frame not in range(4):
        raise ValueError('Unknown menu symbol/frame')
    x = (14, 21, 28, 21)[frame]
    parts = ['<path d="M6 43V10l19-7 19 7v33M6 13h38M10 40h30M6 46h38"/>',
             '<path d="M10 16v20m30-20v20"/>',
             '<path d="M%d 10v4h6v-4m-4 4v3h2v-3"/>' % x]
    if name == 'project-klipper':
        parts += ['<path d="M16 20v17m0-8 16-9M22 26l11 11" stroke-width="2.2"/>']
    else:
        parts += ['<path d="M16 21h18L16 36h18M16 24h9m0 9h9" stroke-width="2.2"/>']
    parts += ['<path d="M%d 43h3" stroke-width="2"/>' % (12+frame*7)]
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
    print('Generated 2 menu marks, 8 exact OLED frames and animated previews')


if __name__ == '__main__':
    main()
