#!/usr/bin/env python3
"""Render the beta.20 OLED layout using actual SFC CSS and compiled pixel helper.
This is an isolated browser demonstration, not a screenshot of a live printer.
No remote requests, printer WebSocket, movement or heat commands are used.
"""
import argparse,base64,hashlib,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--module',type=Path,required=True)
 p.add_argument('--chromium-executable')
 args=p.parse_args()
 comp=ROOT/'frontend/fluidd/navigation/M300OledPreview.vue'
 css=re.search(r'<style scoped lang="scss">(.*?)</style>',comp.read_text(),re.S).group(1)
 css=re.sub(r'//[^\n]*','',css)
 helper=(args.module/'m300-oled-pixels.js').read_text().replace('export ','')
 native=ROOT/'docs/img/oled/klipper_home_xyz.png'
 uri='data:image/png;base64,'+base64.b64encode(native.read_bytes()).decode()
 markup='''<!doctype html><html><head><meta charset="utf-8"><style>
 *{box-sizing:border-box}body{margin:0;background:#262629;color:#ccc;font-family:Arial,sans-serif}
 .px-3{padding-left:12px;padding-right:12px}.pb-3{padding-bottom:12px}
 header{height:44px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;font-size:12px}
 .hide{font-size:11px}#card{width:980px}
 '''+css+'''</style></head><body><section id="card">
 <header><span>OLED M300</span><span class="hide">HIDE</span></header>
 <div class="m300-oled-display-row px-3 pb-3"><div class="m300-oled-viewport">
 <canvas class="m300-oled-frame" id="screen"></canvas></div>
 <div class="m300-oled-zoom-controls" role="group">
 <button class="m300-oled-zoom-button">×1</button><button class="m300-oled-zoom-button">×2</button><button class="m300-oled-zoom-button">×3</button>
 </div></div></section></body></html>'''
 js=helper+'''\nwindow.renderDemo=async (uri,zoom)=>{
 const image=new Image();image.src=uri;await image.decode();
 const layout=oledPixelLayout(window.devicePixelRatio,zoom);
 drawOledPixels(document.querySelector('#screen'),image,layout);
 document.querySelector('.m300-oled-zoom-controls').style.height=oledPixelLayout(window.devicePixelRatio,1).cssHeight+'px';
 document.querySelectorAll('button').forEach((b,i)=>b.classList.toggle('m300-oled-zoom-button--selected',i===zoom-1));
 return {dpr:window.devicePixelRatio,zoom:zoom,width:layout.width,height:layout.height,cssWidth:layout.cssWidth,cssHeight:layout.cssHeight};
 };'''
 out=ROOT/'docs/img';records=[]
 with sync_playwright() as pw:
  options={'headless':True,'args':['--no-sandbox','--force-device-scale-factor=1']}
  if args.chromium_executable:options['executable_path']=args.chromium_executable
  browser=pw.chromium.launch(**options)
  page=browser.new_page(viewport={'width':1020,'height':400},device_scale_factor=1)
  page.route('**/*',lambda route:route.abort())
  page.set_content(markup);page.add_script_tag(content=js)
  for zoom in (1,2,3):
   layout=page.evaluate('(a)=>window.renderDemo(a.uri,a.zoom)',{'uri':uri,'zoom':zoom})
   target=out/f'fluidd_oled_beta20_x{zoom}.png'
   page.locator('#card').screenshot(path=str(target))
   records.append({'file':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'layout':layout})
  version=browser.version;browser.close()
 report={'reference_release':'v1.0.0-beta.20','source_commit':'4828a9da9d5fd8b0b93eb2ac267732ee7e49d506',
 'kind':'Isolated browser demonstration using production SFC stylesheet and compiled pixel helper; no live printer',
 'physical_printer':False,'browser':'Chromium '+version,
 'component_sha256':hashlib.sha256(comp.read_bytes()).hexdigest(),
 'pixel_helper_source_sha256':hashlib.sha256((ROOT/'frontend/fluidd/navigation/m300-oled-pixels.ts').read_bytes()).hexdigest(),
 'source_image':str(native.relative_to(ROOT)),'screens':records}
 (ROOT/'docs/reports/FLUIDD_OLED_DEMO.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':'PASS','screens':len(records)}))
if __name__=='__main__':main()
