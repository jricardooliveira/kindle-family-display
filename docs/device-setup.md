# Kindle Paperwhite 11th generation

The user identified a Paperwhite 11th generation (PW5). Native portrait output is 1236×1648, rotation 0; landscape can use rotation 90. The private configuration now targets portrait. Defaults in the generic sample remain 800×600.

Resolution is supported by [KOReader's Kindle device implementation](https://github.com/koreader/koreader/blob/master/frontend/device/kindle/device.lua). [Amazon's device identification page](https://digprjsurvey.amazon.com/csad/help/node/GK33S847NN4V6Y83) identifies the 11th-generation Paperwhite as a touchscreen device released 2021. Use touch navigation; do not plan physical page-turn button mappings.

The user confirmed firmware 5.16.7, an existing jailbreak and KOReader already installed. The exact KOReader version remains unknown. Client integration can use that existing installation; no firmware or jailbreak changes are required for the server work.

Server output is configured and tested independently of device access. To fetch it from the Kindle, the host needs a private LAN binding rather than 127.0.0.1; the exact server address is still needed.

Pending physical checks: home Wi-Fi access, fetching `/kindle/current.png`, fullscreen display with the intended orientation, touch navigation across News/Weather → Family → Calendar, refresh cadence, sleep/wake behavior and recovery when the server is unavailable. Use a synthetic local image for the first device check.

## Current deployment

The dashboard runs as a Docker Compose service on the Debian home server (`~/homelab/kindle-hub`), bound to that server's private LAN address on port 8000; `scripts/deploy.sh` updates it. Output is the landscape design rendered at 1648×1236 and rotated 90° into a 1236×1648 image.

The Kindle uses the KOReader TRMNL plugin with the server as its base URL. The plugin fetches `/api/display`, shows the returned image full screen and repeats at the server's refresh rate. It has no navigation: screens rotate on the server's timer and a tap closes the image.

Still to confirm on the device: orientation (90 or 270), type rendering on e-ink, that the plugin follows the five-minute rate, and sleep/wake recovery.
