# M300 Classic RC26 · Fluidd sidebar in OrcaSlicer

WebKit can retain a failed module load across an ordinary page reload. After a sidebar import error RC26 fetches the local view assets from the web server again before opening the selected page. The browser test serves an actual HTTP 404, clicks Console, simulates two successive Klipper restarts over Moonraker and clicks the toolbar reload button.

The Console, History and Settings sidebar items also work while a print is paused. When an already open page tries to fetch an obsolete view module after an update, clicking the item loads a fresh page at the selected route and preserves the printer address. Fluidd now recognizes successive Klipper restarts from the disconnect and ready notifications sent over the same Moonraker connection. The circular arrow in the top bar lets you reload the current page inside the Device tab.

In the existing Orange Pi deployment checkout run:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Open the updated page once to load the new toolbar. The web-only update is independent of the host version displayed by the information macro. MCU 1.0.8 and `MCU/M300_SD.zip` remain available for firmware installation. The historical illustrated manual includes screenshots from beta.20.
