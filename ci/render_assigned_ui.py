#!/usr/bin/env python3
"""Render production OLED views using offline test fixtures; never run printer I/O."""
import argparse
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    args=parser.parse_args()
    package=args.package.resolve()
    sys.path[:0]=[str(package/'tests'),str(package)]
    from PIL import Image, ImageDraw, ImageFont
    from types import SimpleNamespace as NS
    from test_settings_information import session

    out=Path(__file__).resolve().parents[1]/'docs/assets/ui-symbols'
    font=ImageFont.truetype('DejaVuSans.ttf',18)
    title_font=ImageFont.truetype('DejaVuSans-Bold.ttf',25)
    frames=[]
    for phase in range(4):
        samples=[]
        for kind in ('oled','led','fan','info','mesh','heat','file','probe'):
            with session() as h:
                if kind in ('oled','led'):
                    h.menu.page='setting_'+kind+'_brightness'
                    h.oled.selection=12 if kind=='oled' else 8
                    title=('OLED brightness / 12 of 16' if kind=='oled' else 'LED brightness / 8 of 16')
                elif kind=='fan':
                    h.run('ZORTRAX_FAN_TEST_START');h.action('TOGGLE_UPPER');h.p._tick(h.now)
                    h.oled.selection=1;title='Fan test / selected upper fan enabled'
                elif kind=='info':
                    h.menu.page='info_printer';h.oled.selection=0
                    h.board.hardware.get_status=lambda:dict(hardware_label='HW05',serial_number='DEMO0001',factory_print_minutes=90)
                    title='Printer information / illustrative values'
                elif kind=='mesh':
                    status=dict(state='PROBING',busy=True,result=None)
                    h.objects['m300_pad_mesh']=NS(get_status=lambda now:dict(status))
                    h.menu.page='bed_mesh';h.oled.selection=0;title='Bed mesh / native pad probing active'
                elif kind=='heat':
                    h.run('ZORTRAX_HEAT');h.p._tick(h.now);title='Heat the extruder / active heating'
                elif kind=='file':
                    status=dict(state='IMPORTING',busy=True,token='preview',filename='sample.zcode',
                        source='host',bytes_copied=1024,format=None,targets={},error=None)
                    h.objects['m300_models']=NS(get_status=lambda now:dict(status))
                    h.menu.page='model_file';h.oled.selection=0;title='Model file / active preparation'
                else:
                    h.oled.message=('Probe error','No trigger on probe after full movement')
                    title='Reported probe failure / explanatory icon'
                h.oled._render(h.now+phase*.5)
                wire=h.oled._render_wire
                image=Image.frombytes('L',(256,64),bytes(level*17 for byte in wire for level in (byte>>4,byte&15)))
                samples.append((title,image))
        sheet=Image.new('RGB',(1120,840),'#0b1118')
        draw=ImageDraw.Draw(sheet)
        draw.text((32,24),'Assigned OLED screens',font=title_font,fill='#eaf5ff')
        draw.text((32,60),'Production renderer · 16-segment controls · 50 × 50 symbols · 500 ms frames',font=font,fill='#a8c0d2')
        for index,(title,image) in enumerate(samples):
            x,y=32+(index%2)*544,108+(index//2)*178
            draw.text((x,y),title,font=font,fill='#eaf5ff')
            sheet.paste(image.convert('RGB').resize((512,128),Image.Resampling.NEAREST),(x,y+30))
        draw.text((32,814),'Offline illustrative fixtures. No physical printer was operated.',font=font,fill='#a8c0d2')
        frames.append(sheet)
    frames[0].save(out/'assigned_oled.png')
    frames[0].save(out/'assigned_oled.gif',save_all=True,append_images=frames[1:],
                   duration=500,loop=0,disposal=2,optimize=False)
    print('Rendered eight assigned OLED views and their four-frame animation')


if __name__=='__main__':
    main()
