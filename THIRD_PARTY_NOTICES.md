# Third-party notices and runtime components

The **VirtualGlove Controller (Arduino UNO Q)** hosts the camera and
recognition runtime described below.

VirtualGlove's original source code and associated documentation are
licensed under the repository's MIT License. That license does not replace the
licenses or terms that apply to third-party software and model files.

## What an ordinary release distributes

| Item | Included in release | Licence and notice |
| --- | --- | --- |
| VirtualGlove source, documentation, and original artwork | Yes | MIT; see `LICENSE` |
| MediaPipe 0.10.35 ARM64/Python 3.12 wheel | Yes | Apache 2.0; the wheel retains its own licence and the release includes `licenses/Apache-2.0.txt` |
| Google Hand Landmarker model | Yes | Apache 2.0; see `licenses/Apache-2.0.txt` and the model record below |
| VirtualGlove Nestopia patch and reproducible build recipe | Yes | GNU GPL version 2; see `licenses/GPL-2.0.txt` |
| Compiled `lr-nestopia-powerglove` core | Built on RetroPie when the user selects native support; not bundled in the Controller archive | GNU GPL version 2; the installer preserves upstream copying information with the installed core |
| `uhubctl` | Installed from Debian only when the camera-recovery option is used; not bundled | GNU GPL version 2 or later, under the Debian package's own notices |
| RetroArch, FCEUmm, stock Nestopia, and RetroPie | Already supplied by or installed through RetroPie; not bundled | Their respective upstream licences |
| Arduino platform and libraries listed below | Downloaded by the Arduino toolchain; not bundled in the Controller archive | Their respective upstream licences |

Keep `LICENSE`, this notice, `licenses/Apache-2.0.txt`, and
`licenses/GPL-2.0.txt` with redistributed copies. The application does not
distribute ROM images, original game artwork, or Nintendo software.

## MediaPipe 0.10.35 ARM64 wheel

A wheel (`.whl`) is an installable Python package. VirtualGlove ships one
compiled Linux ARM64 MediaPipe runtime, so the VirtualGlove Controller does
not build MediaPipe during installation. The `cp312-cp312` tags identify
CPython 3.12 and its binary interface; `linux_aarch64` identifies ARM64 Linux.

```text
python/worker-wheels/mediapipe-0.10.35+powerglove.cpu1-cp312-cp312-linux_aarch64.whl
```

| Property | Value |
| --- | --- |
| Component | MediaPipe 0.10.35 for CPython 3.12, Linux ARM64 |
| Upstream project | <https://github.com/google-ai-edge/mediapipe> |
| Upstream source commit | `f8ef212d5c962c0e853db7e59d217056b187084b` |
| License | Apache License 2.0 |
| VirtualGlove packaged-wheel SHA-256 | `6d29bfc33daebd8e47ff9a75d09ae8c032cdcc74445ba365c5aa78a85a6a2d2e` |

### Modification notice

The ARM64/Python 3.12 wheel was built from the identified upstream source for
the UNO Q environment. It retains upstream source headers and MediaPipe's full
Apache 2.0 license at
`mediapipe-0.10.35+powerglove.cpu1.dist-info/licenses/LICENSE`. The build keeps
the established MediaPipe Hands graph used by VirtualGlove and includes
the narrow Linux compatibility and GPU-research support recorded in the
[Engineering Journey](docs/ENGINEERING_JOURNEY.md).
Production selects the four-thread XNNPACK CPU graph; the slower GPU lanes are
not selected during gameplay.

The release wheel was then repackaged for the headless Controller. Its `RECORD`
integrity list was rebuilt after these metadata changes:

- The unused `jax` dependency declaration was removed.
- The unused `jaxlib` dependency declaration was removed.
- Headless OpenCV was pinned to `opencv-contrib-python-headless==4.11.0.86`.

Removing unused JAX dependencies avoids a large first-start download and
reduces pressure on the Controller's storage. The rebuilt wheel was imported on
the ARM64 Controller, reported MediaPipe `0.10.35+powerglove.cpu1` and OpenCV
`4.11.0`, and confirmed that JAX was absent. Do not substitute another wheel
without repeating dependency, camera, recognition, replay, and thermal tests.

## Google Hand Landmarker model

VirtualGlove uses Google's float16 Hand Landmarker task bundle.

| Property | Value |
| --- | --- |
| VirtualGlove Controller runtime path | `data/models/hand_landmarker.task` |
| Official download | <https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task> |
| SHA-256 | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| Size | 7,819,105 bytes |

The unmodified model is preserved in `models/hand_landmarker.task` and included
in the App Lab installation ZIP. Its Apache 2.0 license is in
`licenses/Apache-2.0.txt`; this guide records its source, checksum, and licensing
evidence. Google's official Hand Landmarker
[documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)
links a [model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20%28Lite_Full%29%20with%20Fairness%20Oct%202021.pdf)
that explicitly states Apache License, Version 2.0 on page 2. The project's MIT
license does not replace that license. No model modifications were made.

When vision is first activated, the application verifies and copies the bundled
model into private, persistent `data/models/`. A verified cached copy is reused.
A damaged cache is replaced from the bundle; a damaged bundle is rejected.
Google's pinned download is used only when no bundled model is available.
**Gestures off** does not open or install the model. Wi-Fi deployments preserve
`data/` and include the bundled recovery copy. The model therefore does not
require internet access in a complete installation package; Python and other
first-install dependencies may still require downloads.

`scripts/fetch-runtime-assets.sh` follows the same bundled-first policy and
verifies the pinned checksum before installing the private cached copy.
`models/SHA256SUMS` records the preserved model's digest. Keep the model, license,
notices, and checksum together in backups. Store a copy of the recovery archive
on another drive or in your regular off-machine backup; copies on the same Mac
do not protect against loss of that Mac.

## Verified VirtualGlove Controller sketch toolchain

The September 4, 2026 sketch build and firmware deployment used these pins from
`sketch/sketch.yaml`:

- Arduino Zephyr platform **1.0.0**
- Arduino_RouterBridge **0.4.3**
- Arduino_RPClite **0.3.0**
- ArxContainer **0.7.0**
- ArxTypeTraits **0.3.2**
- DebugLog **0.8.4**
- MsgPack **0.4.2**

The build resolved Arduino_LED_Matrix **0.1.3** from that platform. Preserve the
dependency pins when synchronizing with App Lab; its shortened generated
configuration is not a replacement for the project's complete configuration.
Revalidate compilation and device operation before changing a pin.

Ordinary UNO Q release archives redistribute two unmodified artifacts from the
Arduino Zephyr platform 1.0.0: the UNO Q loader
`zephyr-arduino_uno_q_stm32u585xx.elf` and
`variants/arduino_uno_q_stm32u585xx/flash_sketch.cfg`. The latter retains its
Arduino copyright and Apache-2.0 SPDX header. The platform source is
<https://github.com/arduino/ArduinoCore-zephyr/tree/1.0.0>; its Apache 2.0
license is included as `licenses/Apache-2.0.txt`. The adjacent release manifest
records exact sizes and SHA-256 values. VirtualGlove's separately compiled
Matrix sketch remains MIT-licensed project code; its linked Arduino libraries
retain their upstream licenses.

| Redistributed platform artifact | SHA-256 |
| --- | --- |
| `zephyr-arduino_uno_q_stm32u585xx.elf` | `39d4a4fd47241663323f6e04f94dd8f5a9f9ad6582cf1df37f9709b74026adcd` |
| `flash_sketch.cfg` | `38706cee1f9ff2e53364a47129d1c1aea9bb9687ed26d7d70b4a9f9bc5bca60c` |

## Modified Nestopia libretro core

The optional `lr-nestopia-powerglove` core is built from libretro Nestopia
revision `5a1cd378cb46ca9ccc2dd6f8b2b6a79ab986052e`. Nestopia identifies its
license as the GNU General Public License, version 2. VirtualGlove's MIT
license does not replace the license of Nestopia or the resulting modified core.
The corresponding licence text is distributed as `licenses/GPL-2.0.txt`.

| Property | Value |
| --- | --- |
| Component | libretro Nestopia with the VirtualGlove native-state patch |
| Upstream project | <https://github.com/libretro/nestopia> |
| Pinned revision | `5a1cd378cb46ca9ccc2dd6f8b2b6a79ab986052e` |
| Upstream license | GNU General Public License, version 2 |
| Local modification | `native/nestopia-powerglove/nestopia-powerglove.patch` |
| Patch SHA-256 | `1ed4eb4bc803a4d445b6e5a1c7b22ccb00cf8a18d465954730282212b8334c06` |
| Modified upstream files | `libretro/libretro.cpp`; `source/core/input/NstInpPowerGlove.cpp` |
| Modification ledger | This guide, under **Nestopia modification ledger** |
| Build recipe | `scripts/build-nestopia-powerglove.sh` |
| Built core name | `nestopia_powerglove_libretro.so` on RetroPie |
| Installed core directory | `/opt/retropie/libretrocores/lr-nestopia-powerglove/` |

Ordinary releases contain the patch and build recipe, not a compiled core. If
the user accepts the RetroPie installer's optional native-core step,
the target machine downloads the pinned upstream source, including its author
notices and `COPYING` file, applies the patch, and builds for its own processor.
The core installer places `COPYING` and this consolidated VirtualGlove
notice and modification ledger beside the installed binary. The original
Nestopia copyright/GPL header in
`NstInpPowerGlove.cpp` remains byte-for-byte intact, and the build stops if a
future patch changes it. Stock Nestopia remains untouched and FCEUmm remains
available.

If prebuilt cores are published in the future, produce separately identified
artifacts for every tested RetroPie architecture. Accompany each binary with
the exact complete corresponding source archive used to build it, the local
patch and build instructions, all upstream notices, and the GPLv2 license. A
Git commit or patch URL alone is not the project's binary-distribution plan.
ROM images are never part of a source or binary core artifact.

At runtime, RetroArch loads the custom core only for an explicitly selected ROM.
The launch entry passes the read-only latest-sample file through
`VIRTUALGLOVE_NATIVE_STATE`; the default path is `/run/virtualglove/native-state`.
The patch registers a separately named **VirtualGlove** controller and
identifies the library as **Nestopia PowerGlove**. Invalid, stale, uncalibrated,
lost-tracking, or wrong-profile samples are neutralized. The compatibility
record in [Super Glove Ball native compatibility](docs/super-glove-ball-native.md)
separates exact-ROM-confirmed X/Y/Z and hand-pose packet behavior from wrist and
button fields that remain unmapped.

The local patch changes only `libretro/libretro.cpp` and
`source/core/input/NstInpPowerGlove.cpp`. SHA-256 values for both pristine
upstream files are recorded below. The build applies the
patch only after checking out the pinned commit, rejects unrelated source-tree
changes, and verifies that Nestopia's original 22-line Power Glove copyright
and GPL header remains byte-for-byte identical.

### Nestopia modification ledger

This additive record does not replace Nestopia's source-file headers, copyright
notices, Git history, or `COPYING` file. At the pinned revision,
`NstInpPowerGlove.cpp` begins with Martin Freij's original 2003-2008 copyright
and GPL notice. The patch begins after that complete header and leaves it
byte-for-byte unchanged. The protected pristine files have these SHA-256 values:

- `libretro/libretro.cpp`:
  `3e6356e56d1c25e2266be155ea2a0a3155d971e60eecba946026422957f5a25f`
- `source/core/input/NstInpPowerGlove.cpp`:
  `7328ab1cc9cc902ac129d217c4d47faa247d2d6e7d41b8d8ac7eb634c097e7cd`

The September 4 `libretro.cpp` changes added the versioned latest-sample
structure; coherence, profile, calibration, detection, and freshness checks;
neutral invalid-input behavior; a separately selectable controller; calibrated
X/Y plus Start and Select delivery; the `Nestopia PowerGlove` identity; and
callback cleanup. The matching `NstInpPowerGlove.cpp` changes enable native
input only when `VIRTUALGLOVE_NATIVE_STATE` is present, provide the exact-ROM
ten-byte stream while retaining Nestopia's ordinary twelve-byte path, and add
opt-in trace hooks without altering normal latch processing. Cabinet testing
corrected camera-to-Nestopia Y orientation; unknown fields remained neutral and
FCEUmm remained available.

The September 5 changes added closed-hand and index-point flags without changing
the version-1 record size. A five-finger fist maps to packet byte 5 `$FF`, index
point to `$0F`, and open or ambiguous poses to `$00`. Calibrated depth maps to
absolute signed packet byte 3 with the camera-facing sign reversed. The exact
ROM repeatedly received `$00` open, `$FF` fist, `$0F` index point, and fist plus
forward-Z (`$81`) Power Punch candidates; lost or stale tracking remained fully
neutral.

A September 6 diagnostic option inserts checked hooks after the normal patch.
Project-owned `diagnostic_trace.h` records callback validity, sequence and
publication identities, and local consumption time, then exports a private CSV
on game unload. It does not modify the production patch, upstream headers,
native-state ABI, or normal selection and is active only for an explicitly
diagnostic build and trace environment.

VirtualGlove 0.4.0 requires matching signed-controller software on both
computers, but its coordinate-efficiency work does not change this patch or
require a rebuild. The confirmed ten-byte packet is documented in
[Super Glove Ball native compatibility](docs/super-glove-ball-native.md#confirmed-exact-rom-packet).
Bytes 7-8 retain Nestopia's fixed `$00` initialization; their gameplay role is
not established.

Future changes must remain in the local patch and be appended here. Do not
replace or prepend project ownership over an upstream header. Keep upstream
notices and licenses with source and binary distributions. The guarded build
stops if the protected Nestopia Power Glove header changes.

## uhubctl

The VirtualGlove Controller host installer uses the distribution-provided
`uhubctl` command to detect and operate genuine USB per-port power switching.
The helper never bundles or modifies this utility, and it never forces it to
operate on a hub that it does not report as supported.

| Property | Value |
| --- | --- |
| Component | `uhubctl` USB hub per-port power control utility |
| Upstream project | <https://github.com/mvp/uhubctl> |
| License | GNU General Public License, version 2 |
| Installed by | Debian package manager on the VirtualGlove Controller host |
| Tested repository candidate | Debian 13 ARM64 `uhubctl` 2.6.0-1 |
| Distribution boundary | Not copied into VirtualGlove source or release archives |

The root helper first asks `uhubctl` about the exact allowlisted hub location
and camera port without using its force option. Only a positive capability
result permits a port cycle. Unsupported hardware retains the project's
identity-checked whole-hub driver fallback. Debian remains responsible for the
installed binary and accompanying copyright and license files.

## External RetroPie emulator dependencies

VirtualGlove uses RetroPie-provided emulator software but does not include
those binaries in its installation archives. When either dependency is absent,
the RetroPie installer can ask the user's existing RetroPie Setup installation
to install it. That operation remains governed by RetroPie and the upstream
licenses.

| Component | VirtualGlove use | Upstream and license | Distribution boundary |
| --- | --- | --- | --- |
| RetroArch | Libretro frontend used to load FCEUmm and `lr-nestopia-powerglove` | [RetroArch](https://github.com/libretro/RetroArch), GPLv3 | Installed by RetroPie; not modified or redistributed by VirtualGlove |
| FCEUmm | Default NES core for standard D-pad/button mappings and the complete Super Glove Ball fallback | [FCEUmm](https://github.com/libretro/libretro-fceumm), GPLv2 | Stock RetroPie core; not modified or redistributed by VirtualGlove |

The deterministic direction benchmark separately builds stock FCEUmm revision
`236ccdfc911e84c60fea6b9d0699c2d440a8de14` in an isolated working directory.
That pin makes the benchmark reproducible; it does not replace the user's
RetroPie core, install FCEUmm, or make the benchmark binary a release artifact.

<!-- PAGEBREAK -->

## Updating runtime components

### MediaPipe wheel or Hand Landmarker model

Before publishing a wheel or model update, complete these steps. The
[command reference](docs/CONFIGURATION_REFERENCE.md#build-inspect-or-maintain-project-files)
explains the build and verification scripts.

1. Record the official source URL, version, license, size, and SHA-256 here.
2. Update the pinned values in `src/powerglove_vision/runtime_assets.py`, `scripts/fetch-runtime-assets.sh`, `scripts/verify-app-lab-package.py`, and `models/SHA256SUMS` when changing the model.
3. If repackaging another wheel, record every difference from upstream and retain its license files.
4. Build the App Lab installation ZIP and confirm it contains one wheel, the verified model, its license and notices, and only the root `sketch/` application sketch.
5. Test first-launch offline model installation, download fallback, and checksum verification, background preloading with capture off, first activation after reboot, camera initialization, tracking, the Glove Academy and Dashboard pages, and controller output on the VirtualGlove Controller before publishing the package.

### Modified Nestopia core

Before changing the Nestopia revision or native patch:

1. Select an exact upstream commit from the official libretro Nestopia repository. Record the commit, upstream license, affected pristine-file SHA-256 values, and new patch SHA-256 in this document.
2. Update the identical revision pin in `scripts/build-nestopia-powerglove.sh`, this modification ledger, tests, and compatibility/benchmark documents. Do not use a moving branch or tag as the build identity.
3. Rebase `native/nestopia-powerglove/nestopia-powerglove.patch` onto a clean checkout. Preserve all upstream headers and notices. The guarded build must still reject changes to the original `NstInpPowerGlove.cpp` header.
4. Run the native-core, state-bridge, installer, selection, exact-ROM trace, safe-neutral, and direction-response tests. Reconfirm packet length, detection, bit order, boundaries, timing, X/Y/Z orientation, open/fist/index values, Start behavior, tracking-loss release, and the explicit FCEUmm rollback on the cabinet.
5. Build the RetroPie installation archive and verify it contains the patch, build/install recipes, this modification ledger, and upstream notices, but no ROM or compiled core. If publishing a binary separately, provide the exact complete corresponding source and GPL materials described above.

When the benchmark FCEUmm pin changes, record the new official revision in the
benchmark document and rerun both the native and standard-joypad lanes. Normal
RetroPie FCEUmm and RetroArch upgrades remain the responsibility of RetroPie;
retest controller selection and fallback gameplay before claiming compatibility.

<!-- PAGEBREAK -->

## Documentation and website assets

The following assets support the guides and browser interface. Their origins
are recorded separately from the software, model, and firmware dependencies above.

### Documentation illustration provenance

The gesture sheets under `docs/images/gestures/` were generated on September 3,
2026 with OpenAI's image-generation tool from project-authored prompts, then
selected and arranged for the VirtualGlove gameplay guide. They are
documentation assets, not runtime dependencies. No game screenshots, scans,
box art, characters, publisher logos, or other source images were supplied to
the generator.

The individual gestures and original Pixel Pal mascot under
`docs/images/gestures/v2/` were generated on September 4, 2026 with the same
built-in tool, using the project's generated contact sheet as a style reference.
Their prompts are preserved in `docs/images/gestures/v2/prompts.json`. The
earlier illustrations remain available in their original locations.

The index-curl illustration was subsequently redrawn using a user-supplied
hand photograph as its pose reference. Only the illustrated glove is included;
the reference photograph is not distributed with the project.

The repository applies its MIT License to these curated project assets to the
extent the project owner has rights in them. Game names and other third-party
marks remain the property of their respective owners.

### Application screenshots

All application screenshots in `docs/images/` were refreshed from the current
VirtualGlove source on September 6, 2026. They cover Dashboard, local Rock Paper Scissors, Glove Academy,
personalization, players and hand-setup restoration, Setup and guided pairing,
Games, and the Help library. `scripts/capture-guide-screenshots.py` renders the
real page templates in an isolated browser with temporary player state and
sample telemetry. Camera areas use an explicit “Camera preview omitted”
placeholder; no live camera, cabinet, or personal settings are accessed.
The script also invokes `tests/browser_setup_pairing.py --screenshots` for
pairing states using non-secret fixtures. These captures document the interface,
not live delivery or hardware verification. Gesture illustrations and physical
matrix photographs remain unchanged. No runtime dependencies are added.

### Website icon

The website icon in `assets/virtualglove-icon.png` was derived from the
project's `assets/virtualglove-logo.png` on September 6, 2026 using OpenAI's
image-generation tool. It isolates the hand-and-target emblem without the
wordmark. Browser-tab and Apple touch icon variants were resized from that
square artwork. `assets/favicon.ico` contains 16, 32, and 48 pixel variants and
is the single browser-tab icon declared by the shared page template. The Apple
touch icon is separate. Setup and Help use the same root-relative icon URL;
there is no Setup-specific asset directory. Setup is served directly at `/setup`,
without a query revision or redirect. Older query-string bookmarks still work.
The original logo remains unchanged.
