# Zortrax M300 Classic v1.0.0-beta.20 — centered OLED and pinned zoom controls

Supersedes beta.19. Frontend visual revision: `OLED-ZOOM-2`. This is a **Fluidd-only layout correction**.

## Layout and color

The same ×1 / ×2 / ×3 buttons now remain **at the right edge of the OLED card, vertically below HIDE**, while the 256×64 OLED viewport is horizontally centered in the **whole card**, not in the leftover space beside the controls. Equal 40 px left/right CSS-grid gutters eliminate the previous asymmetric flex layout. If the enlarged image is wider than its center column, **only the image scrolls horizontally**; the buttons stay pinned in the right column.

The *whole* button column always has the height of the smallest **×1** canvas, independently of whether ×1, ×2 or ×3 is selected. That height follows display DPR: **68 CSS px at DPR 1, 66 CSS px at DPR 2** (including the 2-device-pixel dark guard on each edge), not a fixed 68 CSS px under every browser zoom. Three evenly divided button rows fit this height.

Colors now come from the project's **actual 16-level indexed OLED palette**, not a separately invented teal: foreground/highest brightness `#16A1FE`, low border `#0A436C`, selected fill `#0C588E` and native background `#020610`.

## What stays unchanged

The square native pixels and browser zoom-aware integer device-pixel mapping from beta.17/19, the fast `NAV-EVENT-1` navigation channel, the PNG decode/painter pipeline, animations, browser-local selection, the physical OLED, all MCU/host sources, UART/SPI, Klipper statuses, the beta.18 Tune/mesh fixes, and all print procedures remain unchanged. The update adds no printer commands, heater moves or calibration work.

## Upgrade the standard beta.19 Orange Pi installation

Only when the printer is **idle and Ready**:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with **Cmd+Shift+R**. No MCU flashing or Moonraker configuration changes are required.

## Validation and limitations

Before release, the matching CI must pass host/MCU/ARM/native Klippy checks, strict frontend lint and type checks, component assertions for stable ×1-height toolbar, image/PNG reuse, real Chromium/Firefox layout geometry at multiple card widths, zooms and DPRs, existing pixel-raster comparisons, production Fluidd, and package integrity. These are code and browser checks, **not a physical-printer test**. At zoom ×2/×3 in a narrow card, the complete enlarged OLED cannot fit at once; horizontal image scrolling is intentional.
