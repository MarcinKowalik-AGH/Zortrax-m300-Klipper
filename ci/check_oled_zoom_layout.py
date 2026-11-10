#!/usr/bin/env python3
"""Verify the actual M300 OLED Vue stylesheet: centered screen, pinned controls.

Uses the production pixel helper plus CSS extracted from the Vue component.
Does not communicate with the printer or patch the Fluidd UI at runtime.
"""
import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
* { box-sizing: border-box; }
body { margin: 0; padding: 17px; background: #262629; }
.px-3 { padding-left: 12px; padding-right: 12px; }
.pb-3 { padding-bottom: 12px; }
.header { display: flex; align-items: center; justify-content: space-between;
          height: 43px; color: #eee; padding: 0 12px; }
<!-- REAL_COMPONENT_CSS -->
</style></head><body>
<section id="card" style="width: 378px">
  <div class="header"><span>OLED M300</span><span id="hide">HIDE</span></div>
  <div class="m300-oled-display-row px-3 pb-3">
    <div class="m300-oled-viewport" id="viewport">
      <canvas class="m300-oled-frame" id="oled"></canvas>
    </div>
    <div class="m300-oled-zoom-controls" role="group" id="controls">
      <button class="m300-oled-zoom-button" type="button">×1</button>
      <button class="m300-oled-zoom-button" type="button">×2</button>
      <button class="m300-oled-zoom-button" type="button">×3</button>
    </div>
  </div>
</section>
</body></html>"""

JS = """
const source = document.createElement('canvas');
source.width = 256;
source.height = 64;
const sourceCtx = source.getContext('2d');
sourceCtx.fillStyle = '#020610';
sourceCtx.fillRect(0,0,256,64);
sourceCtx.fillStyle = '#16a1fe';
sourceCtx.fillRect(7,8,190,22);
window.testOledLayout = (width,zoom) => {
  document.getElementById('card').style.width = width+'px';
  const p=oledPixelLayout(window.devicePixelRatio,zoom);
  const canvas=document.getElementById('oled');
  drawOledPixels(canvas,source,p);
  const controls=document.getElementById('controls');
  const small=oledPixelLayout(p.dpr,1);
  controls.style.height=small.cssHeight+'px';
  const buttons=controls.querySelectorAll('button');
  for (const button of buttons) button.classList.remove('m300-oled-zoom-button--selected');
  buttons[zoom-1].classList.add('m300-oled-zoom-button--selected');
  const viewport=document.getElementById('viewport');
  viewport.scrollLeft=0;
  const rect=(el) => {
    const r=el.getBoundingClientRect();
    return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,
            width:r.width,height:r.height,center:(r.left+r.right)/2};
  };
  const before=rect(controls);
  viewport.scrollLeft=99999;
  const after=rect(controls);
  return {
    zoom, dpr:p.dpr, scale:p.scale, smallHeight:small.cssHeight,
    card:rect(document.getElementById('card')),
    viewport:rect(viewport), canvas:rect(canvas), controls:before, afterScroll:after,
    hide:rect(document.getElementById('hide')),
    buttonHeights:Array.from(buttons,b=>rect(b).height),
    buttonColors:Array.from(buttons,b=>getComputedStyle(b).color),
    border:getComputedStyle(controls).borderTopColor,
    selectedBackground:getComputedStyle(buttons[zoom-1]).backgroundColor,
    scrollWidth:viewport.scrollWidth, clientWidth:viewport.clientWidth
  };
};
"""


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', type=Path, required=True)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    component=args.component.read_text()
    assert 'data-preview-revision="NAV-PIPELINE-2"' in component
    assert 'data-zoom-controls="OLED-ZOOM-2"' in component
    assert component.index('class="m300-oled-viewport"') < component.index('class="m300-oled-zoom-controls"')
    assert ':style="zoomControlsStyle"' in component
    css_match=re.search(r'<style scoped lang="scss">(.*?)</style>',component,re.S)
    assert css_match
    css=re.sub(r'//[^\n]*','',css_match.group(1))
    assert 'grid-template-columns: 40px minmax(0, 1fr) 40px;' in css
    module=(args.module/'m300-oled-pixels.js')
    assert module.is_file(), 'Run TypeScript compiler for the real pixel module first'
    source=module.read_text().replace('export ','')
    report=[]
    with sync_playwright() as driver:
        for browser_name in ('chromium','firefox'):
            for requested_dpr in (1,1.25,2):
                options={'headless':True}
                if browser_name=='chromium':
                    options['args']=[f'--force-device-scale-factor={requested_dpr}','--window-size=1100,700']
                else:
                    options['firefox_user_prefs']={'layout.css.devPixelsPerPx':str(requested_dpr)}
                browser=getattr(driver,browser_name).launch(**options)
                try:
                    page=browser.new_page(viewport={'width':1100,'height':700})
                    page.set_content(HTML.replace('<!-- REAL_COMPONENT_CSS -->',css))
                    page.add_script_tag(content=source+'\n'+JS)
                    for width in (378,520,940):
                        for zoom in (1,2,3):
                            v=page.evaluate('(a)=>window.testOledLayout(a.width,a.zoom)',
                                            {'width':width,'zoom':zoom})
                            p=v['dpr']
                            tolerance=max(0.75,1.1/p)
                            assert abs(v['viewport']['center']-v['card']['center'])<=0.6, v
                            assert abs(v['controls']['right']-v['hide']['right'])<=tolerance, v
                            assert abs(v['controls']['top']-v['viewport']['top'])<=tolerance, v
                            assert abs(v['controls']['height']-v['smallHeight'])<=tolerance, v
                            assert abs(v['afterScroll']['right']-v['controls']['right'])<=0.1, v
                            assert max(v['buttonHeights'])-min(v['buttonHeights'])<=0.6,v
                            assert all(h >= 14 for h in v['buttonHeights']), v
                            assert all(c=='rgb(22, 161, 254)' for c in v['buttonColors']),v
                            assert v['border']=='rgb(10, 67, 108)',v
                            assert v['selectedBackground']=='rgb(12, 88, 142)',v
                            canvas=v['canvas']; viewport=v['viewport']
                            if canvas['width']<=viewport['width']+tolerance:
                                assert abs(canvas['center']-v['card']['center'])<=tolerance,v
                            else:
                                assert v['scrollWidth']>v['clientWidth'],v
                            report.append({
                                'browser':browser_name,'requested_dpr':requested_dpr,
                                'actual_dpr':p,'card_width':width,'zoom':zoom,
                                'toolbar_height_css_px':v['controls']['height'],
                                'screen_centered':True,'right_aligned_to_hide':True,
                                'square_device_pixel_scale':v['scale'],'status':'PASS'
                            })
                    page.close()
                finally:
                    browser.close()
    result={'status':'PASS_OLED_CENTERED_FIXED_HEIGHT_CONTROLS',
            'cases':len(report),'physical_hardware_tested':False,
            'results':report}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(report)}))


if __name__=='__main__':
    run()
