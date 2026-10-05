# Resource validation

The goal is less than **200 MB (200,000,000 bytes)** for the running container, including refresh. Compose uses `190m` = 190 MiB = 199,229,440 bytes, with the same memory+swap limit (no swap allowance).

## Image choice

Alpine is the default after its binary dependencies, Portuguese font and Europe/Lisbon timezone support built and ran successfully. The initial ARM64 image was about 107 MB versus 197 MB for Debian slim. Those are uncompressed image sizes, **not RAM measurements**. Alpine uses musl rather than glibc, so dependency compatibility is checked through actual builds/tests; see the [official Python image documentation](https://hub.docker.com/_/python).

## Reproduce the memory exercise

Build the normal production image, then run the checked-in probe against it. The probe starts the actual app and HTTP server, renders all three screens 20 times and performs 240 PNG requests through eight client threads. It verifies decoded grayscale image dimensions, clean shutdown and reports cgroup v2 memory peaks/OOM counters. The in-process test client overhead is included, so this is conservative relative to clients running on Kindles.

```sh
docker build -t kindle-hub:local .
docker run --rm --network none --memory 190m --memory-swap 190m \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --tmpfs /tmp:size=32m,mode=1777 \
  -v "$PWD/scripts:/checks:ro" \
  kindle-hub:local python /checks/check_resources.py
```

Repeat with `-e SCREEN_WIDTH=1648 -e SCREEN_HEIGHT=1648 -e SCREEN_ROTATION=90` before the image name to exercise the current maximum supported dimensions. Use 1236×1648 for the identified Paperwhite. The probe uses temporary storage; regular Compose uses persistent volumes. The functional test suite separately checks failure preservation, restart timestamps, invalid settings, critical alert protection and source-free image requests.

## Deployment acceptance

Record image ID, CPU architecture, dimensions, refresh count, request concurrency, `memory.peak`, `memory.events`, and limit/swap settings. Zero OOM events and a working service matter; merely observing a configured limit is not a pass. The current local host is Apple ARM64 with a Linux Docker VM. Repeat on the Debian Beelink N100 before claiming its hardware has been validated. AI and long-term operation need new measurements when implemented. The live collector slice has its own results below.

## Verified local results — 2026-10-04

Production image: `sha256:0aeee6b7bdc24bce1319a972890ab13b9c7709049378967f3d9c8b197fae5e71`, 106,808,675 bytes (~107 MB uncompressed), Python 3.12.13 / Alpine 3.22.4, ARM64 Linux Docker VM.

| Dimensions | Rotation | Cgroup peak bytes | Peak MB (decimal) | OOM / OOM-kill / limit-hit events |
|---|---:|---:|---:|---|
| 800×600 | 0° | 54,747,136 | 54.75 | 0 / 0 / 0 |
| 1600×1600 | 90° | 76,910,592 | 76.91 | 0 / 0 / 0 |

Each run completed 20 refresh cycles and 240 HTTP PNG requests with eight client threads, external networking disabled, read-only root, dropped capabilities, UID 10001, 199,229,440-byte RAM limit and zero swap allowance. This is a short demo workload, not an indefinite soak or a measurement of live collectors.

Verification: 61 tests passed locally and in Alpine/Python 3.12; lint, formatting and type checks passed. One test-client library deprecation warning remains; it does not affect the production runtime. Compose built, became healthy and preserved every screen timestamp/metadata across restart. Visual review covered 800×600 and 320×240 after correcting calendar text overlap. Astra reviewed architecture/cache/lifecycle and the integrator verified the renderer correction.

The Compose check caught string-valued `SCREEN_ROTATION` failing validation; a regression test now covers all four values from the environment and loading `.env.example`. The final measurements use the corrected image above.

The N100 and the actual Kindle remain untested. Repeat the exercise there and after adding AI.

## Verified data collection results — 2026-10-04

Final image: `sha256:cac5cb6936885f61f10980cc85812d8d729d3bf70ad9bfd3aa7e7b41f2df694e`, 112,334,939 bytes uncompressed (~112 MB). This remains image storage, not RAM.

The fixture-fed live pipeline exercises all eight permitted source slots: six calendars with 256 events each (1,536 total), one weather response and one RSS feed with 64 entries. Source intervals are 1 minute during the probe, so the 20 refresh cycles repeatedly collect and normalize while serving 240 PNG requests through 8 client threads. Source counts and decoded grayscale PNG dimensions are asserted. External network is disabled; fixtures contain no family data.

| Dimensions | Rotation | Cgroup peak bytes | Peak MB (decimal) | OOM / OOM-kill / limit-hit events |
|---|---:|---:|---:|---|
| 800×600 | 0° | 66,396,160 | 66.40 | 0 / 0 / 0 |
| 1600×1600 | 90° | 84,402,176 | 84.40 | 0 / 0 / 0 |

Both final runs used ARM64 Linux, UID 10001, read-only root, dropped capabilities, a 190 MiB RAM limit, zero swap allowance, a 64-process limit and an 8 MiB temporary filesystem. Durations were 9.13 s and 11.54 s. This is a short fixture workload, not an indefinite soak or measurements of every possible upstream payload. The DNS deadline uses at most one daemon resolver worker; timed-out DNS cannot accumulate threads or block shutdown.

```sh
docker build -t kindle-hub:local .
docker run --rm --network none --memory 190m --memory-swap 190m \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 64 --tmpfs /tmp:size=8m,mode=1777 -e RESOURCE_LIVE=1 \
  -v "$PWD/scripts/check_resources.py:/probe.py:ro" \
  -v "$PWD/tests/fixtures:/fixtures:ro" \
  kindle-hub:local python /probe.py
```

Add maximum-dimension/rotation environment values as in the earlier procedure. Real configured sources were separately fetched and normalized on host and in Compose without printing calendar content or subscription URLs. The running service reported fresh successful calendar/weather/RSS snapshots, three grayscale image endpoints and healthy status. There are no events in the current 14-day calendar horizon; a valid empty result is preserved as successful data.

Host checks: 156 tests, lint, formatting and types pass. All 156 tests also passed on Alpine/Python 3.12 using a separate test image; production contains no test tools. Astra reviewed source privacy, SSRF/DNS bounds, recurrence work bounds, invalid interval rejection, source fingerprints and stale forecast behavior; regression tests cover the findings. AI remains disabled. Repeat on the Debian N100 and actual Kindle before claiming physical-device acceptance.

## Paperwhite native size — 2026-10-04

The identified Paperwhite 11th generation uses 1236×1648 portrait pixels. Settings and rendering now accept up to 1648 pixels per axis, with defaults unchanged for generic installations. Image `sha256:e05586fe447cccb2191ac2b6f3d9856998458072e736fc039ed35f1d5de5c52b` passed 170 host tests, lint, format and type checks. Running Compose is healthy and all three endpoints emit 1236×1648 grayscale PNGs from the private configuration.

The same eight-source synthetic workload (1,536 calendar events, 20 refresh cycles, 240 requests/eight client threads, network disabled, 190MiB limit/no swap, 8MiB tmpfs) measured:

| Dimensions | Rotation | Peak bytes | Peak MB | OOM / limit-hit events |
|---|---:|---:|---:|---|
| 1236×1648 | 0° | 76,386,304 | 76.39 | 0 / 0 |
| 1648×1648 | 90° | 87,683,072 | 87.68 | 0 / 0 |

These remain ARM64 Linux-VM server tests; Kindle display/refresh and Debian N100 hardware validation are pending. Firmware and jailbreak/KOReader status are needed before device client setup.
