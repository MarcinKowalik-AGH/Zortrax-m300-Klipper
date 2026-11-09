#!/usr/bin/env python3
"""Combine 21 archived PCB PNGs with 27 additional board photographs."""
from pathlib import Path
from PIL import Image
import zipfile, hashlib, io, json

ROOT = Path("hardware/M300_Dual/photos")
BASE = ROOT / "M300_Dual_Photos_21_PNG_GitHub_compact.zip"
EXTRA = ROOT / "additional"
OUT = ROOT / "M300_Dual_Photos_48_PNG.zip"
REQUIRED_NEW = [8997, 8998, 8999] + list(range(9001, 9025))

def to_png(raw):
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail((950, 950), Image.Resampling.LANCZOS)
        data = io.BytesIO()
        image.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(data, "PNG", optimize=True)
        return data.getvalue()

old = {}
with zipfile.ZipFile(BASE) as archive:
    for entry in archive.namelist():
        if entry.lower().endswith(".png"):
            old[Path(entry).name] = archive.read(entry)
if len(old) != 21:
    raise SystemExit(f"Expected 21 original PNGs, found {len(old)}")

new, missing = {}, []
for number in REQUIRED_NEW:
    candidates = list(EXTRA.glob(f"IMG_{number}.*")) + list(EXTRA.glob(f"IMG_{number} *.*"))
    candidates = sorted(p for p in candidates if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not candidates:
        missing.append(number)
    else:
        new[f"IMG_{number}.png"] = to_png(candidates[0].read_bytes())
if missing:
    raise SystemExit(f"Missing {len(missing)} new photographs: {missing}")

photos = {**old, **new}
if len(photos) != 48:
    raise SystemExit(f"Expected 48 photos, found {len(photos)}")

manifest = [{"file": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(photos.items())]
with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for name, data in sorted(photos.items()):
        archive.writestr(name, data)
    archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    archive.writestr("README.md", "# Zortrax M300 Dual hardware photos\n\n48 PNG photos: 21 original and 27 additional; EXIF/GPS removed.\n")
print(f"PASS {len(photos)} PNG photos, {OUT.stat().st_size} bytes, SHA256={hashlib.sha256(OUT.read_bytes()).hexdigest()}")
