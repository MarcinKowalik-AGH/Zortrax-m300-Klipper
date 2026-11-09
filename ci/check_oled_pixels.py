#!/usr/bin/env python3
"""Actual browser screenshots: every source OLED pixel is an equal N x N block.

Exercises the same compiled drawOledPixels helper used by the Vue component.
DPR represents page zoom/display density; OS magnifiers and transient pinch
compositing are deliberately not claimed. No connection to a printer.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

HTML = '''<!doctype html><html><head><style>
body { margin: 0; background: #ddd; }
#viewport { margin: 23.13px 17.17px; width: 817.3px; overflow-x: auto; padding: 4px; }
canvas { display: block; margin: 0 auto; image-rendering: pixelated; }
</style></head><body><div id="viewport"><canvas id="oled"></canvas></div>
<script type="module">
import { oledPixelLayout, drawOledPixels } from './m300-oled-pixels.js';
const native = document.createElement('canvas'); native.width = 256; native.height = 64;
const ctx = native.getContext('2d');
const data = ctx.createImageData(256, 64);
for (let y=0; y<64; y++) for (let x=0; x<256; x++) {
  const i=(y*256+x)*4;
  data.data[i]=(x%2)*255; data.data[i+1]=(y%2)*255;
  data.data[i+2]=((x+y)%3)*127; data.data[i+3]=255;
}
ctx.putImageData(data,0,0);
window.testPixels = (width) => {
  document.querySelector('#viewport').style.width=width+'px';
  const p = oledPixelLayout(window.devicePixelRatio), canvas=document.querySelector('#oled');
  drawOledPixels(canvas,native,p);
  const r=canvas.getBoundingClientRect();
  return {...p,left:r.left,top:r.top,actualWidth:r.width,actualHeight:r.height};
};
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browsers', default='chromium,firefox')
    parser.add_argument('--chromium-executable')
    args = parser.parse_args()
    root = args.module.resolve()
    module = root / 'm300-oled-pixels.js'
    if not module.is_file():
        raise SystemExit('Compile the exact production pixel helper first')
    script = HTML.split('<script type="module">', 1)[1].split('</script>', 1)[0]
    script = '\n'.join(line for line in script.splitlines() if not line.startswith('import '))
    script = module.read_text().replace('export ', '') + '\n' + script
    markup = HTML.split('<script type="module">', 1)[0] + '</body></html>'
    source = Image.new('RGB', (256, 64))
    source.putdata([((x % 2)*255, (y % 2)*255, ((x+y) % 3)*127)
                    for y in range(64) for x in range(256)])
    results = []
    with sync_playwright() as playwright:
        for name in args.browsers.split(','):
            for ratio in (0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.3333333, 1.5, 1.75, 2, 2.5, 3, 4):
                # Set real renderer DPI. CDP device_scale_factor emulation can
                # resample screenshots without updating the renderer's physical
                # pixel grid (devicePixelContentBoxSize), invalidating this test.
                options = {'headless': True}
                if name == 'chromium':
                    options['args'] = [f'--force-device-scale-factor={ratio}', '--window-size=1200,600']
                    if args.chromium_executable:
                        options['executable_path'] = args.chromium_executable
                elif name == 'firefox':
                    options['firefox_user_prefs'] = {'layout.css.devPixelsPerPx': str(ratio)}
                browser = getattr(playwright, name).launch(**options)
                try:
                    context = browser.new_context(no_viewport=True)
                    page = context.new_page()
                    page.set_content(markup)
                    page.add_script_tag(content=script)
                    page.wait_for_function('typeof window.testPixels === "function"')
                    for width in (817.3, 607.7):
                        layout = page.evaluate('(w) => window.testPixels(w)', width)
                        # Capture the whole page: Firefox keeps a fixed device-pixel
                        # window in no_viewport mode. At high DPR the centered
                        # canvas can extend beyond its visible CSS viewport.
                        screenshot = page.screenshot(full_page=True)
                        image = Image.open(io.BytesIO(screenshot)).convert('RGB')
                        # Some engines quantize the requested scale factor: use the reported DPR.
                        dpr = layout['dpr']
                        left = round(layout['left']*dpr) + layout['guard']
                        top = round(layout['top']*dpr) + layout['guard']
                        expected = source.resize((layout['width'], layout['height']), Image.Resampling.NEAREST)
                        # Compositors may choose the adjacent device-pixel origin for
                        # a fractional CSS box. Locate that origin, but still compare
                        # EVERY native-image pixel (including its first/last rows).
                        match = None
                        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1),
                                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
                            actual = image.crop((left+dx, top+dy,
                                                 left+dx+layout['width'], top+dy+layout['height']))
                            box = ImageChops.difference(actual, expected).getbbox()
                            if box is None:
                                match = [dx, dy]
                                break
                        if match is None:
                            args.output.parent.mkdir(parents=True, exist_ok=True)
                            image.save(args.output.parent / f'OLED_PIXELS_FULL_{name}_{ratio}.png')
                            actual.save(args.output.parent / f'OLED_PIXELS_FAIL_{name}_{ratio}.png')
                            raise AssertionError(f'{name} DPR={ratio}, width={width}: unequal/interpolated pixels at {box}; {layout}')
                        results.append({'browser': name, 'requested_dpr': ratio, 'dpr': dpr,
                                        'column_width': width, 'integer_scale': layout['scale'],
                                        'screenshot_size': list(image.size),
                                        'compositor_origin_delta': match,
                                        'screen_pixels_verified': layout['width']*layout['height'], 'status': 'PASS'})
                    context.close()
                finally:
                    browser.close()
    report = {'status': 'PASS_BROWSER_INTEGER_OLED_PIXELS', 'tests': len(results),
              'compiled_helper_sha256': hashlib.sha256(module.read_bytes()).hexdigest(),
              'physical_printer_tested': False,
              'scope': 'Actual Chromium/Firefox screenshot raster at explicit DPR and two fractional column widths; not OS/pinch compositor scaling',
              'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'tests': len(results)}))


if __name__ == '__main__':
    main()
