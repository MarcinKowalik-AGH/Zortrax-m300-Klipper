# Optional M300 USB camera

Connect a UVC USB camera to the Linux Klipper host. Camera support is disabled
by default. Regular M300 installation and host updates do not install a
streamer or enable video.

On the current verified `orange-pi` branch, as the KIAUH/Klipper account:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-camera.py --enable --apply
```

In a `main` source checkout run `python3 ci/install_camera.py --enable --apply`.
Without `--apply` the command only prints a plan. The installer installs
Debian/Armbian packages `ustreamer` and `v4l-utils`, detects one USB capture
camera, enables `m300-camera.service` and adds **M300 USB** to Moonraker/Fluidd.
Refresh Fluidd and enable the camera card in its dashboard layout if hidden.

Edit `~/printer_data/config/m300_camera.conf` in Fluidd to configure it:

```ini
[camera]
enabled: True
device: auto
resolution: 640x480
fps: 10
format: auto
port: 8088
fluidd_port: 4480
```

Apply edits with `python3 install-camera.py --apply`. Set `enabled: False`
to stop and disable streaming and the Fluidd view, or run
`python3 install-camera.py --disable --apply`. The file is read by the
camera installer; do not include it in `printer.cfg`. Saving it alone or
restarting Klipper does not apply changes. Use `--data` for another KIAUH
data directory. Device autodetection saves a stable path when available.
For multiple cameras specify `--device /dev/v4l/by-id/...-video-index0`.

Start with 640×480 at 10 fps; use 1280×720 if supported by your camera.
`format: auto` prefers hardware MJPEG and otherwise uses YUYV. Explicit
`MJPEG` and `YUYV` are supported. Check formats with
`v4l2-ctl --device /dev/video0 --list-formats-ext`.

New cameras default to **UV4L-MJPEG Stream** (`uv4l-mjpeg`), which displays
the existing ustreamer feed without the regular MJPEG Stream worker. This
display mode was confirmed working with the M300 camera in OrcaSlicer 2.5.2
after regular MJPEG failed in the Device tab.

For an existing camera, select **Settings → Cameras → M300 USB → UV4L-MJPEG
Stream** in Fluidd, save and refresh Device. Keep `/m300-camera/stream` and
`/m300-camera/snapshot` unchanged. Subsequent `install-camera.py --apply`
preserves the selected display type, including UV4L-MJPEG, MJPEG Adaptive
and regular MJPEG. Existing cameras are not automatically migrated.

The local backend binds to 127.0.0.1:8088. A managed nginx block on the
existing Fluidd port exposes `/m300-camera/stream`, `/m300-camera/snapshot`
and `/m300-camera/state`. No Klipper/MCU changes or restarts are required;
Moonraker registers the view through its API without restarting. Video
runs as the Klipper account with the `video` group and lower CPU priority.
The installer tests nginx, live capture and JPEG retrieval through the
Fluidd proxy. Failure restores the previous nginx and camera service.
Backups are stored beside the configuration in `m300-camera-backup-*`.

Inspect errors with `journalctl -u m300-camera.service -n 80 --no-pager`.
If another streamer such as Crowsnest owns the same device, stop it first
or continue using your existing streamer. This installer does not stop
unrelated services. Use `--nginx-site /etc/nginx/sites-available/fluidd`
for custom layouts and set the actual `fluidd_port` in the config.

Disabling works without a connected camera or running Moonraker. If
Moonraker is unavailable, the service is stopped and a message asks you
to apply again later to synchronize the Fluidd view.

Software tests cover the optional configuration, device selection, nginx,
API and failure recovery. Testing your physical camera requires running
the installer on the printer host; `video_verified: true` is only printed
after live capture and proxy/snapshot checks pass there.
