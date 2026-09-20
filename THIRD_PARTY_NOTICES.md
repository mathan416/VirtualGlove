# Third-Party Notices

VirtualGlove's original source, documentation, and project artwork are licensed
under the repository's MIT License. That license does not replace the terms
that apply to third-party software, models, firmware components, or tools.

This document records what a release includes, what an installer obtains from
the host system, and the source and license obligations for the modified
Nestopia core. VirtualGlove does not distribute ROM images, Nintendo software,
scanned game artwork, or publisher assets.

## Release contents at a glance

| Component | How VirtualGlove uses it | Distribution and license |
| --- | --- | --- |
| MediaPipe 0.10.35 | Hand landmark recognition on the Controller | Modified ARM64/Python 3.12 wheel included; Apache License 2.0 |
| Google Hand Landmarker | Model used by MediaPipe | Unmodified model included; Apache License 2.0 |
| Arduino Zephyr loader and flash configuration | Loads Matrix firmware on Arduino UNO Q | Two unmodified platform files included; Apache License 2.0 |
| Modified Nestopia libretro core | Native Super Glove Ball input | GPLv2 binary and exact corresponding source included for RetroPie, Recalbox, Batocera, and LaunchBox |
| NumPy and headless OpenCV | Numerical and camera support | Installed as Python dependencies; BSD-3-Clause and Apache License 2.0 respectively |
| evdev | Linux console input support | Installed where required; BSD-3-Clause |
| Python Cryptography | Authenticated LaunchBox communication | Installed in the isolated LaunchBox runtime; Apache License 2.0 or BSD-3-Clause |
| `uhubctl` | Optional USB camera power recovery | Installed from Debian when supported; GPLv2 or later |
| RetroArch, FCEUmm, stock Nestopia, RetroPie, Recalbox, Batocera, and LaunchBox | Console and emulator environment | Supplied separately by the selected platform; their upstream licenses apply |

Keep `LICENSE`, this notice, `licenses/Apache-2.0.txt`, and
`licenses/GPL-2.0.txt` with redistributed VirtualGlove packages. Components
installed by a platform or package manager retain their own notices and license
files.

## Controller recognition components

### MediaPipe 0.10.35 ARM64 wheel

The Controller package includes one compiled MediaPipe wheel, avoiding a
MediaPipe build on the UNO Q during installation. The filename retains its
historical `powerglove.cpu1` build tag because that tag is part of the published
Python package identity; it is not a service, application, or user-facing
product name.

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

#### VirtualGlove modifications

The wheel was built from the identified upstream source for the UNO Q. It
retains upstream source headers and MediaPipe's Apache 2.0 license at
`mediapipe-0.10.35+powerglove.cpu1.dist-info/licenses/LICENSE`.

VirtualGlove repackaged it for a headless Controller and rebuilt its `RECORD`
integrity list after these metadata changes:

- The unused `jax` dependency declaration was removed.
- The unused `jaxlib` dependency declaration was removed.
- Headless OpenCV was pinned to `opencv-contrib-python-headless==4.11.0.86`.

The packaged runtime was verified on ARM64 with MediaPipe
`0.10.35+powerglove.cpu1`, OpenCV 4.11.0, and no JAX installation. Production
uses the four-thread XNNPACK CPU graph. Experimental GPU paths described in the
[Engineering Journey](docs/ENGINEERING_JOURNEY.md) are not selected during
gameplay. Do not replace this wheel without repeating dependency, camera,
recognition, replay, and thermal validation.

### Google Hand Landmarker model

VirtualGlove uses Google's float16 Hand Landmarker task bundle.

| Property | Value |
| --- | --- |
| VirtualGlove Controller runtime path | `data/models/hand_landmarker.task` |
| Official download | <https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task> |
| License | Apache License 2.0 |
| SHA-256 | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
| Size | 7,819,105 bytes |

The unmodified recovery copy is `models/hand_landmarker.task`, and its digest is
recorded in `models/SHA256SUMS`. Its Apache 2.0 license is in
`licenses/Apache-2.0.txt`. Google's official Hand Landmarker
[documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker)
links a [model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20%28Lite_Full%29%20with%20Fairness%20Oct%202021.pdf)
that identifies the Apache License 2.0. No model modifications were made.

When vision first starts, VirtualGlove verifies the bundled model and copies it
into private persistent storage. A damaged cache is replaced from the bundle;
a damaged bundle is rejected. The pinned official download is used only when
no bundled model is available. **Gestures off** does not open or install the
model.

### Python runtime dependencies

VirtualGlove's package metadata is the authoritative dependency list. These
packages are installed from the configured Python package source rather than
copied into the repository.

| Package | Purpose | Upstream license |
| --- | --- | --- |
| NumPy | Numerical arrays used by camera and recognition code | BSD-3-Clause |
| OpenCV headless | Camera capture and image processing without a desktop GUI | Apache License 2.0 |
| evdev | Linux input-device access used by console receivers | BSD-3-Clause |
| Cryptography | Authenticated LaunchBox runtime communication | Apache License 2.0 or BSD-3-Clause |

Installed package metadata and license files remain authoritative for the exact
versions selected by the installer.

## Matrix firmware toolchain

The verified Matrix firmware toolchain is pinned in `sketch/sketch.yaml`:

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
| Patch SHA-256 | `272222b3f55093e901f64228e2adcd82dbedaba77360cf9bfb4c829b6652f706` |
| Windows portability patch | `native/launchbox/nestopia-windows.patch` |
| Windows patch SHA-256 | `88c7bae02bfdb1cda8866dadb676710889da7910a8ac695a2a9eb4b62b72e4e7` |
| Modified upstream files | `libretro/libretro.cpp`; `source/core/input/NstInpPowerGlove.cpp` |
| Modification ledger | This guide, under **Nestopia modification ledger** |
| Build recipe | `scripts/build-nestopia-powerglove.sh`; pinned RetroPie cross-build environments recorded in its manifest; Recalbox and Batocera target/matrix wrappers; Windows target wrapper `scripts/build-launchbox-nestopia-powerglove.sh` |
| Built filename | `nestopia_powerglove_libretro.so` or `nestopia_powerglove_libretro.dll` |

### Binary and source distribution

For redistribution, each bundled binary is accompanied by its exact complete corresponding source,
the local patch, build instructions, upstream notices, and the GPLv2 license.
The manifests are the authoritative checksum ledger.

| Platform | Packaged targets | Authoritative manifest or recipe |
| --- | --- | --- |
| RetroPie | `armv6`, `armv7`, 32-bit `armv8`, `aarch64`, `x86_64` | `native/retropie/manifest.json` |
| Recalbox 10.1 | `rpizero2`, `rpi3`, `rpi4_64`, `rpi5_64`, `rg353x`, `odroidgo2`, `x86_64` | `native/recalbox/manifest.json` |
| Batocera 43.1 | `bcm2835`, `bcm2836`, `bcm2837`, `bcm2711`, `bcm2712`, `x86_64`, `rk3326`, `rk3399`, `rk3568`, `rk3588`, `s905`, `s905gen2`, `s905gen3`, `s922x`, `sm8250` | `native/batocera/manifest.json` |
| LaunchBox | Windows `x86_64` | `native/launchbox/manifest.json` |

Recalbox 10.1 `rpizero2` and every other listed target has a separate binary
and corresponding source record in the manifest.

The verified LaunchBox core has SHA-256
`5828d3885a79dba494dcb772a6693093a069a9ac76e758df5392c3da05834299`.
Its corresponding source archive has SHA-256
`a1c3e574b8b65195dab63d3865bf70d3371a44a059ea7d08ef67b3c6595f5033`.

RetroPie, Recalbox, and Batocera packages select a build for the detected
architecture, verify it against the manifest, and perform a target-side
libretro load and identity check. Compatible later Recalbox and Batocera
releases may reuse the newest packaged build for the same architecture, but
the load check remains the final gate. Failure leaves FCEUmm available.

The optional RetroPie installation verifies the packaged core and matching
source archive for the host processor. The installer places `COPYING`, this
notice, and the modification ledger beside the installed binary. The exact
physically validated Pi 4 binary remains a separate 32-bit ARMv8 artifact;
original Pi 2 hardware receives the ARMv7 build instead. Stock Nestopia is
never replaced.

For every additional prebuilt core, produce a separately identified artifact
for the exact tested operating-system target and architecture. Accompany each binary with
the exact complete corresponding source archive used to build it, the local
patch and build instructions, all upstream notices, and the GPLv2 license. A
Git commit or patch URL alone is not the project's binary-distribution plan.
ROM images are never part of a source or binary core artifact.

<!-- PAGEBREAK -->

Installed locations are platform-specific:

- RetroPie: `/opt/retropie/libretrocores/lr-nestopia-powerglove/`
- Recalbox: `/recalbox/share/system/virtualglove/native/recalbox/TARGET/VERSION/`
- Batocera: `/userdata/system/virtualglove/native/batocera/TARGET/VERSION/`
- LaunchBox: `%LOCALAPPDATA%\VirtualGlove\native\`

### Runtime scope

RetroArch loads the custom core only for a game explicitly assigned to the
native route. The launch entry supplies a read-only latest-sample file through
`VIRTUALGLOVE_NATIVE_STATE`; the default is
`/run/virtualglove/native-state`. Invalid, stale, uncalibrated, lost-tracking,
or wrong-profile samples are neutralized.

The patch registers a separate VirtualGlove controller, identifies the core as
Nestopia PowerGlove where required by the established binary interface, and
selects the native peripheral for the isolated core. The confirmed ten-byte
packet carries X, Y, Z, open hand, fist, index point, and Start behavior. Fields
that the exact ROM does not use remain neutral. The compatibility boundary in
[VirtualGlove Input Modes](docs/INPUT_MODES.md) separates confirmed behavior
from deliberately unmapped fields.

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

The patch adds the versioned latest-sample record, coherence and freshness
checks, safe-neutral handling, a separately selectable controller, native
packet generation, core identity, and callback cleanup. Cabinet validation
corrected camera-to-Nestopia Y orientation. It also added open-hand, fist,
index-point, and calibrated depth delivery without changing the version-1
record size.

An optional diagnostic build inserts checked trace hooks after the production
patch. It records callback, sequence, publication, and consumption timing in a
private CSV. The diagnostic path does not alter upstream headers, the native
state ABI, or normal production selection.

Signed controller protocol changes do not alter this libretro patch or require
a core rebuild unless the native-state ABI itself changes. The confirmed
behavior is documented in
[VirtualGlove Input Modes](docs/INPUT_MODES.md#confirmed-compatibility-boundary).
Bytes 7-8 retain Nestopia's fixed `$00` initialization because their gameplay
role has not been established.

<!-- PAGEBREAK -->

Future changes must remain in the local patch and be appended here. Do not
replace or prepend project ownership over an upstream header. Keep upstream
notices and licenses with source and binary distributions. The guarded build
stops if the protected Nestopia Power Glove header changes.

## System-supplied tools and emulators

### uhubctl

The VirtualGlove Controller host installer uses the distribution-provided
`uhubctl` command to detect and operate genuine USB per-port power switching.
The helper never bundles or modifies this utility, and it never forces it to
operate on a hub that it does not report as supported.

| Property | Value |
| --- | --- |
| Component | `uhubctl` USB hub per-port power control utility |
| Upstream project | <https://github.com/mvp/uhubctl> |
| License | GNU General Public License, version 2 or later |
| Installed by | Debian package manager on the VirtualGlove Controller host |
| Tested repository candidate | Debian 13 ARM64 `uhubctl` 2.6.0-1 |
| Distribution boundary | Not copied into VirtualGlove source or release archives |

The root helper first asks `uhubctl` about the exact allowlisted hub location
and camera port without using its force option. Only a positive capability
result permits a port cycle. Unsupported hardware retains the project's
identity-checked whole-hub driver fallback. Debian remains responsible for the
installed binary and accompanying copyright and license files.

### Console and emulator dependencies

VirtualGlove uses console-provided emulator and frontend software but does not
include those binaries in its installation archives. Installation and updates
remain governed by the platform and upstream licenses.

| Component | VirtualGlove use | Upstream and license | Distribution boundary |
| --- | --- | --- | --- |
| RetroArch | Libretro frontend used to load FCEUmm and Nestopia (VirtualGlove) | [RetroArch](https://github.com/libretro/RetroArch), GPLv3 | Installed on the console; not modified or redistributed by VirtualGlove |
| FCEUmm | Default NES core for standard D-pad/button mappings and the complete Super Glove Ball fallback | [FCEUmm](https://github.com/libretro/libretro-fceumm), GPLv2 | Stock console core; not modified or redistributed by VirtualGlove |

<!-- PAGEBREAK -->

The deterministic direction benchmark separately builds stock FCEUmm revision
`236ccdfc911e84c60fea6b9d0699c2d440a8de14` in an isolated working directory.
That pin makes the benchmark reproducible; it does not replace the user's
installed core, install FCEUmm, or make the benchmark binary a release artifact.

## Updating third-party components

Before publishing a third-party update:

1. Pin an official source revision or URL and record its license, size, and
   SHA-256 here or in the platform manifest.
2. Preserve upstream headers, notices, and complete applicable license texts.
3. Record every local modification and rebuild package integrity metadata.
4. Verify that every binary has its exact corresponding source where the
   license requires it.
5. Run package, installer, runtime, security, and hardware acceptance checks.
6. Update this document and rebuild the published Third-party Notices PDF.

For a MediaPipe wheel or model update, also test offline installation, checksum
failure, camera start, recognition, tracking loss, and thermal behavior. For a
Nestopia update, recheck the protected upstream header, native-state ABI, packet
behavior, exact-ROM controls, architecture manifests, target-side load checks,
and FCEUmm fallback. Detailed commands are in the
[Configuration Reference](docs/CONFIGURATION_REFERENCE.md#build-inspect-or-maintain-project-files).

## Documentation and website assets

This section records provenance for project assets. These files are not runtime
dependencies.

### Gesture illustrations and Pixel Pal

The gesture sheets under `docs/images/gestures/` and the individual gesture
illustrations and original Pixel Pal mascot under
`docs/images/gestures/v2/` were generated with OpenAI's image-generation tool
from project-authored prompts. The v2 prompts are preserved in
`docs/images/gestures/v2/prompts.json`, and the original generated contact sheet
was used as the style reference.

The index-curl illustration was subsequently redrawn using a user-supplied
hand photograph as its pose reference. Only the illustrated glove is included;
the reference photograph is not distributed with the project.

Intentional extra-digit variants are retained for Pixel Pal's Extra-Digit Hunt.
No game screenshots, scans, box art, characters, publisher logos, or other
third-party source images were supplied to the generator.

The repository applies its MIT License to these curated project assets to the
extent the project owner has rights in them. Game names and other third-party
marks remain the property of their respective owners.

**Application screenshots and website icon.** Screenshots in `docs/images/`
are generated from VirtualGlove's real page
templates with temporary player state and sample telemetry. Camera regions use
an explicit **Camera preview omitted** placeholder; the capture process does
not access a live camera, cabinet, pairing secret, or personal settings. These
images document the interface rather than proving hardware delivery.
The website icon in `assets/virtualglove-icon.png` was derived from
`assets/virtualglove-logo.png` with the same image-generation tool. Favicon and
Apple touch icon variants were resized from that artwork; the original logo is
unchanged.
