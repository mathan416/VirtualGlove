# VirtualGlove Installation Guide

Install VirtualGlove with one script on the **VirtualGlove Controller
(Arduino UNO Q)** and one on a supported RetroArch console.
The scripts prepare the software and startup helpers; you finish by pairing the
devices, positioning the camera, and testing a game.

Choose **Setup → Matrix attract mode** to keep the idle animation On, Dim it,
or turn it Off except for faint connection pixels. This does not change game
displays, T, L, or gesture recognition. The setting saves without a tracker restart.

For an existing installation, this update changes controller transport on both computers. Stop controller output, update both to matching software, then start and test input. Mixed old/new versions do not deliver input with the default settings. See [signed controller transport and upgrades](CONFIGURATION_REFERENCE.md#signed-controller-transport-and-upgrades) for staged upgrades and rollback.

## Install stable release v0.4.2

Stable release **v0.4.2** retains Programs 1–14, the Ready-to-Play
guide, and the live joystick dead-zone camera grid. It adds source-accurate
rapid-fire defaults and live Dashboard overrides, removes retired protocol and
pre-0.4.1 compatibility paths, avoids repeated configuration and camera scans
during Dashboard polling, and reduces the installed documentation footprint.
Close games and stop controller output, then run the matching command on each
device.

On the VirtualGlove Controller:

```sh
cd /home/arduino
curl -fLO https://github.com/mathan416/VirtualGlove/releases/download/v0.4.2/install-uno-q.sh
bash install-uno-q.sh --version v0.4.2
```

On RetroPie:

```sh
curl -fLO https://github.com/mathan416/VirtualGlove/releases/download/v0.4.2/install-retropie.sh && bash install-retropie.sh --version v0.4.2
```

Verify both report `v0.4.2`, then follow the pairing/first-game checks below.
Existing hand settings and pairing files are preserved. The Controller installer
also updates the matrix firmware. Review [coordinated transport upgrades and
rollback](CONFIGURATION_REFERENCE.md#signed-controller-transport-and-upgrades)
before replacing an older installation.

## v0.5.0 console support under development

VirtualGlove 0.5.0 adds Recalbox 10.x, Batocera 38+, and LaunchBox on Windows x86-64 while retaining
RetroPie. Each console has a separate release installer so the package can
validate the intended operating system before changing it:

| Console | Installer | Persistent VirtualGlove location | Game detection |
| --- | --- | --- | --- |
| RetroPie | `install-retropie.sh` | `/opt/virtualglove-src` and `/etc/virtualglove` | RetroPie runcommand hooks |
| Recalbox 10.x | `install-recalbox.sh` | `/recalbox/share/system/virtualglove` | bounded RetroArch process monitor |
| Batocera 38+ | `install-batocera.sh` | `/userdata/system/virtualglove` | supported `gameStart`/`gameStop` script events |
| LaunchBox | `launchbox/install-launchbox.ps1` | `%LOCALAPPDATA%\VirtualGlove` | LaunchBox RetroArch wrapper |

Recalbox and Batocera publish a separate Linux gamepad named **VirtualGlove
Merged Player 1**. It combines one explicitly selected physical controller with
VirtualGlove, and NES RetroArch uses that one merged device. The original
physical controller continues to operate EmulationStation without duplicate
navigation. LaunchBox retains physical XInput Player 1 plus an audited keyboard
bridge. Player 2 and unrelated RetroArch settings are preserved on every target.

Generic RetroPie continues to publish a separate **VirtualGlove** gamepad. The
cabinet's combined Player 1 merger is a specialized configuration and is not
silently installed on other RetroPie systems.

In the Recalbox/Batocera merger, a physical direction or stick axis wins while
it is active and ordinary buttons combine across both sources. The physical
hotkey has its own merged-device button; VirtualGlove Select can never enable
RetroArch hotkeys. Unplugging the pad releases only its held controls and leaves
VirtualGlove active until the saved controller reconnects. The merged device is
neutral outside RetroArch so EmulationStation sees no duplicate navigation.

Programs 1–14, A–I, Bad Street Brawler, and Super Glove Ball can use the
standard FCEUmm joystick path. Recalbox, Batocera, and LaunchBox also support native Super
Glove Ball through a separately named Nestopia (VirtualGlove) core. Each core
must be built with its target system's own toolchain and load-checked on that
target; neither replaces stock Nestopia. FCEUmm remains the reversible fallback.
The ROM-free native calibration display remains RetroPie-only.

All three platforms use the same authenticated controller transport and game
registry as RetroPie. Their receiver, registry, token, launcher settings, logs,
and startup integration stay in persistent storage rather than the read-only
system image. Updates preserve the token, launcher destination, game registry,
ROMs, saves, and controller configuration.

After installing, the Setup page offers console-specific one-time-code commands.
On Recalbox run:

```sh
sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service pair
```

On Batocera run:

```sh
/userdata/system/services/VirtualGlove pair
```

On LaunchBox run the PowerShell command shown by Setup. It invokes
`%LOCALAPPDATA%\VirtualGlove\launchbox\virtualglove-pair.ps1`. LaunchBox uses
one-time-code pairing only; the Controller never requests a Windows password.

SSH password pairing also recognizes the Linux console systems automatically;
use their normal `root` SSH account. SSH pairing is not offered for LaunchBox.
No console password is retained by the Controller.
Physical validation on the target hardware remains required before v0.5.0 is
published.

### Recalbox native Super Glove Ball

Recalbox 10.1 has seven build targets. Native cores are never shared across
these targets merely because two machines use the same broad CPU family.

| Recalbox target | Typical hardware | Core ABI | VirtualGlove package status |
| --- | --- | --- | --- |
| `rpizero2` | Raspberry Pi Zero 2 and compatible image variants | 32-bit ARM | Included and load-tested |
| `rpi3` | Raspberry Pi 3 family | 32-bit ARM | Included; load-tested on Pi 3, exact `rpi3` image pending |
| `rpi4_64` | Raspberry Pi 4/400 and CM4 | ARM64 | Included and manifest-verified; hardware validation pending |
| `rpi5_64` | Raspberry Pi 5 | ARM64 | Included and manifest-verified; hardware validation pending |
| `rg353x` | Anbernic RG353 family | ARM64 | Included and manifest-verified; hardware validation pending |
| `odroidgo2` | ODROID Go Advance/Super | ARM64 | Included and manifest-verified; hardware validation pending |
| `x86_64` | PCs and Steam Deck | x86-64 | Included and manifest-verified; hardware validation pending |

The package manifest records the Recalbox target and version together with the
ELF class and machine identity. The installer requires all four to agree with
the local machine before it will expose the native core. This permits a release
to carry multiple Recalbox versions for the same hardware target safely.

The release package includes independently built Recalbox 10.1 cores and
complete corresponding source archives for all seven targets. The `rpizero2`
and `rpi3` ARM32 cores both load and report `Nestopia PowerGlove` on the
available Raspberry Pi 3 running the `rpizero2` image; validation on an image
that reports `rpi3` remains outstanding. The five additional cores have passed
manifest, checksum, and ELF-identity validation but have not been claimed as
hardware-tested. Normal Recalbox installation verifies size, SHA-256, exact
target/version and ELF identity, libretro API, and core name before exposing a
core through the reversible runtime overlay. Machines without a packaged
target/version core still install normally and use FCEUmm.

Maintainers can reproduce a target build with the matching official Recalbox
source checkout on a Linux Docker host:

```sh
scripts/build-recalbox-nestopia-powerglove.sh /path/to/recalbox rpizero2
```

Build all seven targets supplied by one exact Recalbox release tree with:

```sh
scripts/build-recalbox-native-matrix.sh /path/to/recalbox
```

Public images may be on different releases. Build those targets separately
from their exact tagged source tree and merge the resulting target/version
entry only after target-side validation.

The builder emits `nestopia_powerglove_libretro.so` and a matching
`manifest.json`. To test a newly built core before promoting it into a future
release, copy both to the appropriate architecture package directory. The
manual target installer remains available for development validation:

```sh
sh /recalbox/share/system/virtualglove/scripts/install-recalbox-nestopia-powerglove.sh \
  /path/to/nestopia_powerglove_libretro.so \
  "/recalbox/share/roms/nes/Super Glove Ball (USA).7z"
```

The installer refuses to run while RetroArch is active, checks the release
manifest, and loads the library on Recalbox before installation. A runtime overlay exposes the separate core in
the read-only core directory and a temporary system list advertises it to
EmulationStation. EmulationStation restarts only when that runtime view first
appears or changes. The exact-ROM `.recalbox.conf` sidecar selects
`nestopia_powerglove`; unrelated ROMs and settings retain their current cores.
On installation and startup, VirtualGlove finds exact Super Glove Ball ROM
filenames from the installed registry and creates the per-ROM selection only
when that ROM has no existing core choice. Upgrades never replace an existing
selection.
To return only that ROM to joystick mode:

```sh
python3 /recalbox/share/system/virtualglove/scripts/configure-recalbox-super-glove-ball-core.py \
  --rom "/recalbox/share/roms/nes/Super Glove Ball (USA).7z" \
  --mode fceumm --apply
```

### Batocera native Super Glove Ball

Batocera's operating-system core directories are read-only, and its cores are
architecture-specific. Build Nestopia (VirtualGlove) from a Batocera source
checkout matching the target image:

```sh
scripts/build-batocera-nestopia-powerglove.sh /path/to/batocera.linux TARGET
```

Use Batocera's target name, such as `bcm2711` for Raspberry Pi 4 or `bcm2712`
for Raspberry Pi 5. The builder initializes only Batocera's stock Nestopia
package and then compiles VirtualGlove's pinned, patched source with that exact
cross-compiler and sysroot. Copy the resulting
`nestopia_powerglove_libretro.so` to the Batocera system, then run as root:

```sh
/userdata/system/virtualglove/scripts/install-batocera-nestopia-powerglove.sh \
  /path/to/nestopia_powerglove_libretro.so \
  "/userdata/roms/nes/Super Glove Ball (USA).nes"
```

The installer first loads the core and checks its libretro ABI. It then places
it atomically in persistent storage, exposes it under the separate
`nestopia_powerglove` name through reversible overlay mounts, and changes only
that exact ROM's Batocera core selection. Stock Nestopia and FCEUmm remain
unchanged. To return the ROM to joystick mode:

```sh
python3 /userdata/system/virtualglove/scripts/configure-batocera-super-glove-ball-core.py \
  --rom "/userdata/roms/nes/Super Glove Ball (USA).nes" --mode fceumm --apply
```

### LaunchBox on Windows x86-64

LaunchBox remains the frontend and 64-bit RetroArch remains the emulator.
Install 64-bit Python 3 with its `py` launcher, place the matching FCEUmm core
in RetroArch, and connect to the Internet for the one-time isolated Python
dependency installation, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\launchbox\install-launchbox.ps1 `
  -LaunchBoxRoot "C:\LaunchBox" -RetroArchRoot "C:\RetroArch"
```

The installer uses the current user's Local AppData folder and preserves an
existing token, game registry, and Controller address. A fresh installation
uses `virtualglove.local`; pass `-ControllerHost` when the Controller has a
different name or fixed address. Configure a LaunchBox emulator whose
application path is
`%LOCALAPPDATA%\VirtualGlove\launchbox\virtualglove-launchbox.cmd`, associate
it with Nintendo Entertainment System, and pass only the ROM path.

The wrapper exact-matches the ROM registry. Ordinary games launch with FCEUmm;
Super Glove Ball launches with the separately named Windows x86-64
`nestopia_powerglove_libretro.dll`. It keeps an authenticated game lease alive
only while that exact RetroArch process runs. Unregistered games still launch
with FCEUmm but do not enable gestures.

For standard FCEUmm games, VirtualGlove injects arrow, X, Z, Enter, and Right
Shift keys into RetroArch Player 1. RetroArch's normal XInput/autoconfiguration
remains enabled, so the physical Player 1 joypad works at the same time. Keys
are emitted only while `retroarch.exe` is foreground and are released when
focus moves elsewhere. The installer and wrapper audit those keys against
RetroArch commands and Hotkey Enable. Any collision disables VirtualGlove for
that launch, records the exact setting, and leaves XInput and the game active. Native
Super Glove Ball instead selects the emulated Power Glove peripheral; its
physical-joypad behavior is not claimed until it is validated on Windows. The
receiver runs in the signed-in user's desktop session; it is not installed as
a Windows service.

Maintainers build the Windows core through the manually dispatched
`launchbox-native-core.yml` workflow or in a MinGW64 environment with:

```sh
bash scripts/build-launchbox-nestopia-powerglove.sh
```

The build applies the common native-glove patch followed by a Windows-only
memory-mapping and monotonic-clock portability patch. The verifier requires a
PE32+ AMD64 DLL carrying the `Nestopia PowerGlove` identity. Import the reviewed
DLL and its generated complete corresponding source archive under
`native/launchbox/x86_64/` before building release packages.

VirtualGlove 0.4.1 is the oldest supported in-place upgrade. The installer
preserves current `/etc/virtualglove` pairing, game-registry, and Controller
settings, but no longer imports pre-0.4.1 `/etc/powerglove` installations.
Unsupported older data is left untouched for manual recovery. A fresh
installation creates only `virtualglove-*` runtime names. Install both devices
from the same release; signed protocol version 2 does not fall back to the
retired unsigned transport.

## 1. Prepare your devices

You need a provisioned VirtualGlove Controller, a supported RetroArch console, a UVC USB camera,
a powered USB hub, and a physical controller for RetroArch setup. Put both devices
on the same trusted local network with internet access. Supply your own games;
no ROMs or BIOS files are included.

For a new Controller, use Arduino App Lab to complete board setup and networking.
Record the console's hostname and the UNO Q's current App Lab address. The
VirtualGlove installer will offer the Controller's permanent friendly name.
Connect the camera through the powered hub.
You do not need to import VirtualGlove through App Lab, install Arduino build
tools, or build a ZIP. The release contains a verified precompiled Matrix image;
the installer checks it and loads it using the UNO Q's factory flashing tools.

Open a terminal on each device, either locally or over SSH. For the Controller:

```sh
ssh arduino@UNO-Q-NAME.local
```

For this initial connection, use the UNO Q name or IP address shown by App Lab.
It may still have its factory name. Use your normal account;
the scripts request your sudo password when administrator access is needed.
They do not store it. Close games before installing. Leave the devices powered
and connected while installation runs; first setup can take several minutes.

The commands below automatically select the latest published stable release from
GitHub. You do not need to enter a release tag or set shell variables. Run both
installers during the same setup session and compare the reported release names;
if a new release appeared between runs, rerun the older installation.
Development prereleases are available separately in the technical reference.
The latest release must include the installer assets before these commands work.

## 2. Run the VirtualGlove Controller installer

Run this single line in the Controller terminal:

```sh
cd /home/arduino
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-uno-q.sh
bash install-uno-q.sh
```

The Controller terminal may open in `/`, where a normal user cannot save files.
The command first moves to the Arduino user's writable home directory so the
installer can be downloaded safely.

The script verifies its download, installs VirtualGlove, and configures automatic
startup. It also installs:

- the precompiled Matrix firmware and early-start hourglass;
- the Shutdown button's system helper;
- guarded camera recovery;
- `uhubctl` for hubs that advertise safe per-port power control.

On a fresh Controller, the installer shows the current board name and suggests
**virtualglove**. Press Enter to use `virtualglove.local`, or enter a different
short name such as `games-room`. Confirm the displayed `.local` address before
installation continues. The installer checks for a visible name conflict on
the current LAN and stops safely if another device is already using it.

This question appears only for a first installation. An update never changes an
established hostname. A non-interactive installation also keeps the existing
board name unless `--hostname NAME` is supplied explicitly.

The terminal connection used for installation can remain open after the rename.
For future browser and SSH connections, use the chosen `.local` name or one of
the IP addresses printed at the end of installation.

Camera recovery is standard and is not presented as an optional prompt. The
camera may be connected after installation, and no separate helper command is
needed. Updates preserve pairing, calibration, and personal tuning. They back up
and replace the supplied `config/profiles.json` baseline so current shared
recognition defaults take effect. The installer never copies a maintainer's
neutral-hand coordinates because those measurements depend on the player's
camera, distance, and position.

During an update, a pending Dashboard shutdown request stops setup before host
helpers are installed. Complete or clear that shutdown request, bring the
Controller back online, and rerun the same installer.

If the script reports a failure, stop and follow its message. If `curl` is missing,
install it with `sudo apt-get install curl ca-certificates`, then retry. The
installer checks compatibility before changing the application.

The ordinary installer also includes first-setup and maintenance support:
camera recovery, pairing and health checks, the optional calibration dot and its
read-only report, aggregate vision status, movement-reach tools, and emulator
configuration. Research replays, protocol traces, soak tests, GPU experiments,
and benchmark drivers remain in the source repository and separate Engineering
Tools download. They are not needed to install, calibrate, play, back up a hand
setup, or update the system.

**Checkpoint:** Open the Dashboard address printed by the installer, normally
`http://virtualglove.local:8088/dashboard`, in your browser.
Dashboard should load. With gestures off, a closed camera is normal. Open
**Play** or **Glove Academy** to check that your camera view and whole hand
appear, then return to Dashboard with controller transmission stopped.

For a first setup, keep the camera choices simple:

- Leave **Camera** on Automatic unless more than one camera is connected.
- Leave **Camera reader** on Recommended — OpenCV.
- Leave frame rate and exposure on Automatic.
- If movement is delayed or tracking drops, run **Find the best camera
  settings** in Setup. Pixel Pal compares only choices supported by that camera
  and does not save a recommendation until you accept it.

Direct V4L2, manual exposure, gain, and buffer comparisons are advanced tools,
not required setup steps. The [Camera Guide](CAMERA_GUIDE.md) explains what they
change in plain language and how to stop or recover a camera test safely.

![Advanced camera settings with Automatic, a discovered camera, and optional manual exposure](images/setup-camera.png)

## 3. Install the console

Choose the one subsection for your console. Install the same published version
on the Controller and console, and close RetroArch first. Repeating the same
installer updates VirtualGlove while preserving pairing, the Controller
destination, game registry, ROMs, saves, and unrelated controller settings.

### RetroPie

Run in the RetroPie terminal as the normal RetroPie user:

```sh
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-retropie.sh && bash install-retropie.sh
```

**Older RetroPie images:** Raspberry Pi OS Buster's Raspbian packages moved to
the legacy archive. The installer detects the obsolete repository and stops
before changing VirtualGlove. Follow [Buster package source moved](TROUBLESHOOTING.md#buster-package-source-moved),
run `sudo apt-get update`, then rerun the same installer. A current RetroPie
image is preferable because Buster no longer receives normal security support.

For a new installation, the script asks for your Controller hostname or IP
address. Enter the `.local` name printed by the Controller installer—normally
`virtualglove.local`. There are no placeholders to replace in the command. An
upgrade that finds `/etc/virtualglove/launcher.json` preserves that destination
and does not ask for it again. Pre-0.4.1 `/etc/powerglove` settings are no
longer imported automatically.

The script installs the receiver, controller mapping, game-launch integration,
and automatic startup. Existing cabinet hooks and controller assignments remain.
It offers missing emulator installation through RetroPie Setup and checks
registered games, including Bad Street Brawler's Glove Zap configuration.

Follow any emulator or game ACTION messages. Missing games do not prevent the
base installation. If asked to launch and exit FCEUmm once, do that and rerun the
installer. If you use another emulator, the installer asks before selecting
FCEUmm for Bad Street Brawler.

If a registered Super Glove Ball ROM is present, the installer also offers the
optional `lr-nestopia-powerglove` core. Accepting installs Git and the standard
build tools, downloads the pinned GPLv2 Nestopia source, applies the included
patch, builds on that RetroPie, and registers a second emulator entry. It does
not change the ROM's saved emulator: FCEUmm remains selected until you choose
`lr-nestopia-powerglove` from RetroPie's per-ROM launch menu. Declining is safe
and leaves the tested joystick fallback unchanged. The build needs internet
access and may take several minutes; no ROM is read or copied by the build.

The installer separately offers **VirtualGlove Calibration Test**. Accept it to
build the small project-owned `lr-powerglove-dot` core and add a ROM-free entry
to RetroPie's **Ports** list. This choice is optional and can be accepted on a
later installer run. It does not select an emulator for any NES game.

**Checkpoint:** The report confirms that receiver startup is configured.
Pairing and live gameplay checks will still be listed as actions.

### Recalbox 10.x

Download `install-recalbox.sh` from the same v0.5.0 release used on the
Controller. Connect to Recalbox as `root`, then run:

```sh
bash install-recalbox.sh --version VERSION --peer virtualglove.local
```

Replace `VERSION` with the published tag and `virtualglove.local` if the
Controller has a different saved name or address. Do not add `sudo`; Recalbox's
SSH session already runs as root. The installer places all managed files in
`/recalbox/share/system/virtualglove`, adds a bounded startup/process monitor to
the persistent `custom.sh`, and asks which configured gamepad is physical Player
1. If exactly one configured gamepad is connected it is selected automatically.
If several are present, list their stable IDs and repeat the install with one:

```sh
bash install-recalbox.sh --version VERSION --list-player1-devices
bash install-recalbox.sh --version VERSION --peer virtualglove.local \
  --player1-device DEVICE-ID
```

The saved identity and EmulationStation mapping do not depend on a changing
`/dev/input/event*` number. At boot, **VirtualGlove Merged Player 1** is created
before a game starts and only the NES Player 1 joypad index is managed. An
upgrade removes only the former eight VirtualGlove keyboard values and backs up
the displaced NES configuration. ROMs, saves, Player 2, and unrelated settings
remain unchanged.

Run the same command without `--peer` for later updates. To check without
changing anything:

```sh
bash install-recalbox.sh --check
sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service status
```

The available Raspberry Pi 3 running Recalbox 10.1's `rpizero2` image has
passed FCEUmm play, native Super Glove Ball, simultaneous physical-joypad use,
and reboot persistence. Other Recalbox targets require their own matching core
and hardware validation.

### Batocera 38 and newer

Download `install-batocera.sh` from the same v0.5.0 release used on the
Controller. Connect to Batocera as `root`, then run:

```sh
bash install-batocera.sh --version VERSION --peer virtualglove.local
```

The installer stores managed files in `/userdata/system/virtualglove`, enables
Batocera's persistent **VirtualGlove** user service, and installs supported
`gameStart`/`gameStop` lifecycle hooks. Controller selection follows Recalbox:
one configured gamepad is automatic; otherwise use
`--list-player1-devices` and `--player1-device DEVICE-ID`. Batocera creates
**VirtualGlove Merged Player 1** before RetroArch and manages only its NES Player
1 assignment. The original physical controller remains the frontend controller.

Run the same command without `--peer` for later updates. To check without
changing anything:

```sh
bash install-batocera.sh --check
batocera-services is-enabled VirtualGlove
/userdata/system/services/VirtualGlove status
```

Batocera hardware and native-core acceptance remain v0.5.0 release gates.

### LaunchBox on Windows x86-64

Install 64-bit Python with its `py` launcher and 64-bit RetroArch with FCEUmm.
Extract the matching VirtualGlove Windows package. In PowerShell, as the same
Windows user who runs LaunchBox, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\launchbox\install-launchbox.ps1 `
  -LaunchBoxRoot "C:\LaunchBox" -RetroArchRoot "C:\RetroArch" `
  -ControllerHost "virtualglove.local"
```

Use the real folders and Controller name. The installer writes only to
`%LOCALAPPDATA%\VirtualGlove`, creates an isolated Python environment, and
preserves its pairing key, registry, and Controller destination on updates.
If Windows requests network permission, allow Private networks only.

In LaunchBox, add **VirtualGlove RetroArch** as an emulator. Set its application
path to `%LOCALAPPDATA%\VirtualGlove\launchbox\virtualglove-launchbox.cmd`,
associate Nintendo Entertainment System, and pass only the ROM path. FCEUmm
keeps RetroArch's physical XInput Player 1 controller while VirtualGlove adds
keyboard controls to the same player. Installation and every wrapped launch
audit the effective RetroArch command and Hotkey Enable bindings. If `Up`,
`Down`, `Left`, `Right`, `X`, `Z`, `Enter`, or Right Shift conflicts,
VirtualGlove is disabled for that launch and the exact conflict is reported;
the physical XInput controller and game remain usable. The receiver runs only
in the signed-in desktop session.

## 4. Pair the devices

The **Controller status** panel at the top of Setup shows the four Off-mode checks in pixel order: app, console service, authenticated response, and Networking. Green means confirmed, red means disconnected or not confirmed, and grey means unknown. Networking reflects a physical Wi-Fi or Ethernet link, including USB dock Ethernet; it is independent of the console checks. These checks do not prove that the game received input.

Both pairing methods below require the six-digit approval PIN shown on the Controller matrix and the certificate-ID comparison. The selected console's one-time code or SSH password is an additional credential. A first visit may show a privacy warning because this is a private local Controller, not a public website.

Pairing gives both devices the same private token. Use the recommended
one-time-code method after both installers finish.

1. Open the secure Setup address printed by the Controller installer, normally `https://virtualglove.local:8443/setup`. Under **Connection and startup**, first choose RetroPie, Recalbox, Batocera, or LaunchBox, then enter that console's hostname or IP address and select **Save connection**. Pairing remains unavailable until both are saved; unsaved edits must be saved first.
2. Continue to **Pair this Controller** in the same card, choose **One-time code (recommended)**, and select **Continue**. Use **Change** beside the saved console to edit its address before starting.
3. In **Confirm your Controller**, compare the `ID` on the physical matrix with the beginning of the browser certificate's SHA-256 fingerprint. Expand **How to compare the certificate** for guidance. If they differ, stop pairing.
4. If they match, check the confirmation box, enter the six-digit **Controller approval PIN** shown after `PN` on the matrix, and select **Continue**.
5. On the saved console, run the single command shown by Setup and leave it running. Enter its 20-character code in **Console one-time code**, then select **Pair with console** within five minutes. Setup shows only the command for the chosen platform: `sudo /opt/virtualglove/bin/virtualglove-pair` on RetroPie, `sh /recalbox/share/system/virtualglove/recalbox/virtualglove-service pair` on Recalbox, `/userdata/system/services/VirtualGlove pair` on Batocera, or the installed `virtualglove-pair.ps1` command on LaunchBox. This single-use code is separate from the Controller approval PIN. Confirm that the terminal belongs to the console named in Setup.
6. Selecting **Pair with console** brings **Pairing in progress** into view while the request runs, followed by **Pairing complete** or an error with retry instructions. Before changing its token, the console verifies that its detected platform matches the saved selection. On success, the receiver was restarted and answered an authenticated controller handshake using the newly installed token; you can open Dashboard when ready. Pairing does not arm controller output or prove that a game received input.

### Optional: remove the browser privacy warning

After the Matrix ID matches the browser certificate, return to **Trust this
Controller** and download the trust certificate. Install it as a trusted root on
that phone or computer, then close and reopen the browser. This is required only
once per browser device and survives ordinary VirtualGlove upgrades and website
certificate renewals. Setup contains current instructions for Apple, Windows,
and Android devices. Never install the certificate if the Matrix comparison
does not match.

After pairing, always complete the game check below. **Pairing complete** proves
that the receiver accepted the shared key; the game check proves that your own
camera, Controller, network, receiver, emulator, and game work together.

![Guided pairing starts with the saved console and a choice of one-time code or SSH password.](images/setup-pairing-method.png)

![Controller confirmation with certificate comparison, matrix approval PIN, and remaining time.](images/setup-pairing-confirm.png)

![Pairing in progress while the request waits for the selected console.](images/setup-pairing-progress.png)

![Pairing complete, with the next step on Dashboard.](images/setup-pairing-complete.png)

The Controller confirmation window lasts two minutes. The console address and
pairing method stay fixed during that window. If it expires, the PIN and password
are cleared; select **Start a new confirmation**. You can change methods after
the window ends. A submitted failure also requires fresh confirmation before
retrying. Existing server PIN attempt limits still apply. If the window expires
while you obtain a console code, repeat confirmation and obtain a new code if
needed; neither credential has an unlimited lifetime.

<!-- PAGEBREAK -->

### Alternative: pair with your console password

Use this route only if the console accepts SSH password login. RetroPie normally
uses `pi` and requires that account to run `sudo`; Recalbox and Batocera normally
use `root`. LaunchBox uses one-time-code pairing only and never asks for a
Windows password.

1. Save both the platform and console address in **Connection and startup**.
2. In **Choose a pairing method**, select **SSH password**, then **Continue**.
3. Complete the same certificate comparison and Controller approval PIN step.
4. In **Pair with your console**, enter the console username and password, then select **Pair with console**.
5. **Pairing in progress** stays visible while the request runs; SSH pairing can take a few minutes. Wait for **Pairing complete**, which includes an authenticated receiver-token check, then check the receiver service or open Dashboard. Errors are brought into view with retry instructions.

The password field is unavailable until certificate confirmation is complete.
The password is used for pairing and is not saved by the Controller. Returning
to **Review Controller confirmation**, a failure, expiry, or leaving the page
clears it. If neither route works, use the
[token-management reference](CONFIGURATION_REFERENCE.md#pairing-and-token-management).

When a submitted pairing attempt finishes, the matrix releases the approval PIN and resumes its normal display. When idle, the glove animation follows your On, Dim, or Off attract setting; active game and status displays still take priority.

### Optional first-game check

Select **Get ready to play** on Setup or Dashboard. The guide helps you confirm
the active player and console, practice safely, center the hand, and try the ten
essential controls before launching a registered game. It saves progress per
player without changing Glove Academy lessons. Each visit checks live readiness
again. Finish practice explicitly before enabling game controls; **Ready to play**
confirms the reported connection and game mode, not game-side input receipt.
If you close the guide early, reopen it to resume or use **Leave guide — keep
controls stopped** to exit the output pause explicitly.

### Connection settings and recovery

**Connection and startup** saves the console platform, address, and startup game
profile, then continues directly into secure pairing. Existing upgraded systems
with an address and token keep operating, but must select and save their platform
before pairing again.
Port, camera, and pairing-key replacement are under **Advanced connection settings**.
**Check console address** only checks name resolution. If loading fails, use
**Reload saved settings**; if a save fails, correct or retry it without losing
fields. Controller Start/Stop and shutdown are on **Dashboard**; Setup keeps
the read-only tracking and output status indicators.

Use your console's `.local` name when possible. If that name stops resolving—or
if DHCP changes a saved numeric address—VirtualGlove can look for the already
paired console on the same local network. Only the secure greeting is broadcast;
hand movements and button states are not. The console must prove that it has the
existing pairing key before delivery resumes. Networks that isolate devices,
separate them into VLANs, or block local broadcasts still require a working name,
a current address, or a router DHCP reservation.

Connection saves restart tracking. The separate **Save attract mode** action
changes only the idle matrix display. Hand setup, players, and backups are in
**Glove Academy**. Existing private settings and calibration remain preserved
through the normal installation/upgrade process; the four-pixel display needs its matching matrix firmware. Extending the fourth pixel to Ethernet only needs the updated Controller app and host sampler. Normal installation
and Wi-Fi deployment also install its unprivileged host status sampler. Receiver
changes take effect only after updating both the console and Controller.

## 5. Calibrate and test a game

1. On Dashboard, select a profile, wait for the camera, and show your hand. On first use, the app collects a neutral reference automatically. Use **Center hand** if your resting position produces unwanted movement or your camera/playing position changed. Hold a relaxed, open hand still at the intended center and distance until the button reports completion.
2. Select **Start controller**. This arms authenticated output; delivery begins only for an active registered game or intentional manual profile.
3. Verify the console receiver using its platform check above. On RetroPie, `grep -A8 -B2 'VirtualGlove' /proc/bus/input/devices` should show the separate **VirtualGlove** device. On Recalbox or Batocera it should show **VirtualGlove Merged Player 1** and the installation check should confirm its current NES joypad index. LaunchBox reports whether its gesture keys are free of command/hotkey collisions.

For a visual calibration check, open **Ports → VirtualGlove Calibration Test**.
The utility selects native coordinate delivery only while it is open. The
yellow dot should follow the hand; the green marker means the receiver has a
fresh calibrated sample. A red X means tracking, calibration, pairing, or the
sample's freshness is not ready. Adjust center or **Movement reach** on the
Controller, then reopen or return to the test. Exit normally to release the
test profile.
4. Use the physical controller to open RetroArch. On generic RetroPie, confirm the separate **VirtualGlove** mapping. On Recalbox and Batocera, confirm NES Player 1 is **VirtualGlove Merged Player 1** while EmulationStation still responds only to the original pad. On LaunchBox, keep physical XInput and the conflict-audited keyboard mappings together.
5. Test D-pad, A, B, Start, and Select in a registered game, then confirm the physical joypad still works. Do not replace the entire RetroArch configuration to repair one binding.

For the first test, confirm the selected Program's control style rather than
assuming every numeric profile uses ordinary hand-position movement:

| Programs | What to expect |
| --- | --- |
| 1, 2, 11, 12 | Position-based D-pad with additional finger combinations; Program 2 also reports centering. |
| 3, 5, 6, 8 | Side movement plus push/pull depth controls. |
| 4, 10 | Finger and wrist poses replace ordinary positional steering. |
| 7 | Open-hand dodging/ducking plus positioned fist punches. |
| 9 | Make a fist once to arm Rad Racer controls; this Program has no rapid fire. |
| 13 | VirtualGlove supplies A/B while the merged physical Player 1 controller supplies movement. |
| 14 | Camera and VirtualGlove output intentionally stay off; use the physical Player 1 controller. |

Rapid A/B defaults on only for explicitly documented pulsed buttons: Program 7
A, Program B A, Program H A/B, and Bad Street Brawler B. Every other profile
defaults off. The registry retains Mattel's explicit off entries for Blaster
Master, Double Dribble, Racket Attack, Ice Hockey, and Alpha Mission. Use the [complete Programs 1-14 gesture cards and
official game index](GAMEPLAY_GUIDE.md#quick-selector-programs-1-14) when confirming a
compound action.

An update preserves any Rapid A/B choices already saved for a registered game.
Those choices continue to override its profile defaults. To adopt the corrected
defaults for that game, launch it and choose **Use profile defaults** on
Dashboard. Rapid A/B controls button repetition only; profile-owned fast turns,
pulsed movement, turbo movement, and compound actions do not change.

<!-- PAGEBREAK -->

**Checkpoint:** A gesture changes the intended control in the running game.
Seeing the device name or a running service alone is not an end-to-end test.
Bad Street Brawler's Glove Zap uses simultaneous Left + Right through the
standard gamepad path. The RetroPie installer checks the game-specific FCEUmm option. Follow any
remaining ACTION message and rerun the installer after resolving it. See [Glove Zap setup](CONFIGURATION_REFERENCE.md#bad-street-brawler-glove-zap).
No extra-trigger assignment or receiver change is required.

A calibration uses 24 geometrically valid hand observations. The Controller
installer includes the validated MediaPipe Hands 0.10.35 ARM64 runtime and
headless OpenCV 4.11; it does not download an older fallback or unused JAX
components. MediaPipe's
displayed score describes handedness certainty rather than position confidence,
so it is not used as a false quality gate. Repeating calibration from the same
position should give closely comparable center, scale, wrist, and jitter values,
but natural landmark variation prevents an exact numeric match. Calibration is
shared by every profile. Closing Dashboard
after this check stops its 5 fps diagnostic preview work without stopping hand
tracking or controller delivery.

For Super Glove Ball testing on RetroPie, enter the launch menu while starting
the ROM and choose either `lr-fceumm` or `lr-nestopia-powerglove`. Recalbox and
Batocera use an exact-ROM selection for FCEUmm or their target-built Nestopia
(VirtualGlove) core. The LaunchBox wrapper makes the same exact registry choice
automatically. FCEUmm uses the
ordinary D-pad and buttons for the whole session. The native core uses absolute
X/Y/Z plus open-hand, fist, and index-point packets. Native movement uses
**Latest coordinate** with MediaPipe Hands and the same saved center and reach.
It validates the palm geometry and clamps it to
that reach before mapping, so movement beyond an edge stays at the edge and a
recovered hand normally starts from its first fresh coordinate. Latest holds
only a contradictory or unusually distant non-forward reacquisition for one
additional fresh result. Adjust native travel separately under **Glove
Academy → Tune gestures → Movement reach**. Full-game cabinet play has
confirmed grab/throw, index fire, and fist-plus-forward Power Punch. Continuous
movement is playable, with further latency refinement still planned. Wrist
rotation and remaining unused native packet fields stay neutral. Shared recognition remains
available to every FCEUmm profile. A per-ROM selection
is remembered, so choose FCEUmm again whenever you want the complete fallback.

Setup → **Camera** offers Automatic, 30 fps, and 60 fps. Automatic is the 0.4.0
default: it tries the tested 30-fps path and then accepts the camera driver's
usable rate if necessary. The active rate is shown while tracking runs. Other UVC
cameras do not need to support both explicit rates. See the
[Camera guide](CAMERA_GUIDE.md) before changing the reader, exposure, or gain.
Dashboard's optional **Show statistics** switch is off by default; leave it off
for the lightest gameplay page and enable it only when reading diagnostics.
Controller transmission remains ahead of Dashboard housekeeping either way;
opening the preview does not select a different MediaPipe preparation path.


## 6. Confirm startup and finish

- Launch a registered game and check the expected profile on Dashboard and the matrix.
- Exit the game and confirm that gestures turn off.
- Reboot both devices normally. Confirm that Dashboard returns and the matrix
  progresses through startup to the selected mode. The early-start helper is
  enabled automatically for this boot.
- Check that your saved tuning and calibration remain available.
- Select **Start controller** when ready and verify movement and buttons in the game.

The installers never reboot or request a shutdown automatically. They check
that the Controller shutdown helper is ready. The tested Arduino UNO Q hardware restarts after a halt;
a disconnected website or blank matrix is not proof that power can be removed.

## Updates and checks

Updates keep an inventory of installed application files. After the first inventory
is created, unchanged obsolete files are backed up and removed; your own changes
are kept and reported. If an update is interrupted, follow its recovery instructions
before trying again.

To update, repeat the same single-line commands on both machines. Each selects
the latest published stable release. Changed managed files are backed up, and the installer prints their
location. It asks before interrupting an active Controller session. Close RetroArch
before updating the console. `config/profiles.json` is intentionally replaced;
saved personal tuning remains in `data/gesture-tuning.json`.

For checks only, use the script you already downloaded:

```sh
# On the VirtualGlove Controller:
bash install-uno-q.sh --check
# On RetroPie:
bash install-retropie.sh --check
# On Recalbox (as root):
bash install-recalbox.sh --check
# On Batocera (as root):
bash install-batocera.sh --check
```

Checks do not download, install, restart, or change anything. They may request
administrator access to inspect protected settings. LaunchBox does not have a
separate system check mode: rerun its per-user installer after closing
RetroArch, then complete the pairing and registered-game checks.

| Report | Meaning |
| --- | --- |
| PASS | The named check succeeded. |
| FAIL | Resolve the problem before proceeding, then rerun the installer or checks. |
| ACTION | Complete the named step, such as pairing, adding games, or checking gameplay. |

A successful technical installation can still report ACTION for the physical
checks. Those checks need you and your cabinet.

If movement feels delayed after installation, use the
[read-only latency baseline](direction-response-benchmark.md#collect-a-live-status-baseline)
before changing sensitivity or video settings. It separates Controller timing
from the receiver, emulator, and display checks and does not enable controls.

For a specific version or a development prerelease, use the
[technical installation reference](CONFIGURATION_REFERENCE.md#versioned-two-script-installation).
It also explains compatibility, package building, backups, and recovery.

## If something does not work

- **Download fails:** confirm that the latest stable release includes installer assets,
  check internet access, and retry. A failed verification installs nothing.
- **Unsupported board software:** complete App Lab provisioning or use a compatible
  project release. Do not bypass the installer's compatibility check.
- **Website does not open:** try the Controller's current IP address instead of its
  hostname. Use HTTP on port 8088 and HTTPS on port 8443.
- **Camera missing:** open Glove Academy and wait for the camera view. The Controller
  host helper automatically enrolls the single UVC camera and its parent hub on
  first successful use, even if no camera was connected during installation.
  After enrollment it makes one guarded recovery attempt during a sustained
  outage. Supported hubs power-cycle only the camera port; non-networking hubs
  may use the identity-checked whole-hub fallback. Success requires a real camera frame, not
  merely a device returning to USB.
  If it remains missing, reconnect or power-cycle the camera and check the powered
  hub and cable. A network-bearing hub is never reset as a unit.
- **No controller in RetroArch:** finish pairing, select Start controller, and
  select VirtualGlove for Port 1 using your physical controller.
- **Partial installation:** correct the reported problem and rerun the same
  release. Keep the printed backup location for recovery.

For diagnostic commands or manual repair, use the
[configuration reference](CONFIGURATION_REFERENCE.md#installation-troubleshooting-commands).

## Read the matrix and open the web pages

| Display | See it | Meaning |
| --- | --- | --- |
| Arduino boot logo | <img src="images/matrix/Boot.jpg" alt="Boot matrix display" width="104"> | System startup, before the app display. |
| System heart | <img src="images/matrix/Heart.jpg" alt="Heart matrix display" width="104"> | System startup is progressing. |
| Pulsing hourglass | <img src="images/matrix/Hourglass.jpg" alt="Hourglass matrix display" width="104"> | VirtualGlove is starting. |
| Lightning and animated glove | <img src="images/matrix/idle-glove.png" alt="Simulated glove matrix display" width="104"> | Gestures are off. The revised animation requires updated matrix firmware. |
| Scanning `L` | <img src="images/matrix/L.jpg" alt="L matrix display" width="104"> | Play or Glove Academy practice is active; controller output is paused. |
| Scanning `T` | <img src="images/matrix/T.jpg" alt="T matrix display" width="104"> | Tune gestures is active; controller output is paused. |
| `1`–`14` | Numeric program code | The corresponding original Programs 1–14 profile is selected. Older firmware safely leaves this display blank. |
| `A`–`I` | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | The corresponding profile is selected; Program A is shown. |
| `BS` | <img src="images/matrix/BS.jpg" alt="BS matrix display" width="104"> | Bad Street Brawler is selected. |
| `GB` | <img src="images/matrix/GB.jpg" alt="GB matrix display" width="104"> | Super Glove Ball is selected. |
| Blank matrix | <img src="images/matrix/Blank.jpg" alt="Blank matrix display" width="104"> | No LEDs are illuminated. Check board power and Dashboard; blank does not confirm shutdown. |
| Pulsing profile code | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | A calibrated hand is being tracked. Confirm controller output separately. |
| Blinking X | <img src="images/matrix/X.jpg" alt="X matrix display" width="104"> | The app has requested an error display. Check Dashboard for the cause. |

See the [Matrix display guide](MATRIX_GUIDE.md) for the complete animations and
startup sequence. An animation does not prove that shutdown has finished.

| Page | Address |
| --- | --- |
| Dashboard | `http://UNO-Q-NAME.local:8088/dashboard` |
| Play | `http://UNO-Q-NAME.local:8088/play` |
| Glove Academy | `http://UNO-Q-NAME.local:8088/learn` |
| Games (lower Setup section) | `http://UNO-Q-NAME.local:8088/setup#games-section` |
| Help and printable manuals | `http://UNO-Q-NAME.local:8088/help` |
| Connection settings | `http://UNO-Q-NAME.local:8088/setup` |
| Secure pairing | `https://UNO-Q-NAME.local:8443/setup` |

Add and manage players in **Setup → Players**. Choose the active player on Dashboard or in Glove Academy before practicing or playing. Progress and hand
sensitivity persist across restarts and normal upgrades. Selecting a player immediately loads their sensitivity, progress, and saved center. Use **Center hand** for a new player or after moving the camera or changing playing position. Restoring a hand-setup backup requires centering unless you explicitly
reuse its calibration with the same camera and playing positions. Backups include
name, center-box size, personal and effective gesture sensitivity, source software
identity, and calibration. VirtualGlove backup version 4 is the only supported
portable format; older formats are rejected without changing the active player.
The web footer reports
exact software and running firmware identities; older firmware may report unavailable.

Choose each player in turn and select **Back up hand setup** to download a
separate file named for that player, such as
`alex-virtualglove-hand-setup.json`. Your browser saves it on the computer, phone,
or tablet you are using, usually in **Downloads** or the folder you choose. To restore, select
the player you want to update, choose **Restore hand setup**, and pick that
player's saved file from your device. Review it before confirming; restore
updates the selected player, rather than adding a new one.

Completing all sixteen lessons replaces the lesson panel with
the **Glove Master** award. **Start again** restores the lessons.

![Setup connection settings and pairing; use HTTPS to enable pairing](images/setup-page.png)

Help serves the public manuals, illustrations, and PDFs locally. **This console**
shows addresses derived from your current browser connection and public device
settings. It never displays the token. The standalone Quick Reference is
excluded from the public package; the live cabinet page supplies local details.


## Play Checklist

1. Power the selected console and VirtualGlove Controller; leave the camera connected to the powered hub.
2. Open `http://UNO-Q-NAME.local:8088/dashboard`.
3. Select the active profile on the Dashboard, then confirm the expected profile and a detected hand. The saved startup profile remains on Setup.
4. On first use, or after changing your camera or playing position, select **Center hand** while holding a comfortable neutral pose. Otherwise reuse the saved calibration.
5. Select **Start controller** when you are ready to arm gesture control.
6. Launch a registered game and confirm its profile code on the matrix. Delivery
   begins only after RetroArch is running and its short initialization guard ends.
7. Select **Stop controller** before adjusting the camera or leaving the cabinet.
8. Read the shutdown limitation before disconnecting power. **Shutdown** requests a graceful halt, but the tested board restarts; an offline website is not proof that it is safe to unplug.

VirtualGlove remembers the player's explicit **Start controller** or **Stop
controller** choice across Controller application and system restarts. A remembered
Start means **armed**, not unconditional output: controls are sent only during a
live registered RetroArch session or after an intentional manual Dashboard profile
selection. A registered game renews its session while RetroArch is running, so an
Controller application restart can reconnect automatically. Game exit, an unknown game,
or an expired session releases all controls and stops delivery without changing the
armed preference. **Stop controller** remains sticky until explicitly started again.
Install the same release on both devices because this behavior uses a matching Controller
worker and the selected console's game-session integration.

Vision and the dashboard keep running while output is unarmed or waiting for a game,
so setup never generates surprise game inputs.
**Shutdown** is different: it halts Linux on the Controller. The tested board automatically restarts; remaining halted is not guaranteed.

## Fresh hardware acceptance test

Use this checklist for a new Controller and newly prepared supported console. It
deliberately starts without relying on settings from the development machines.

1. Install the same release on both devices. The Controller camera may be absent
   during installation; connect it afterward if needed.
2. Run each available installer's final checks. Confirm the Controller website
   opens and the console receiver and game-session integration start normally.
3. Pair once from Setup. Confirm **Saved console**, **Console service**, and
   **Authenticated response**, then download the privacy-safe system report.
4. Create or rename Player 1, center the hand, set movement reach if desired, and
   complete a few Academy lessons. Restart the Controller and confirm those choices
   remain while controller output stays safely gated.
5. Launch one registered FCEUmm game and Super Glove Ball with the native core.
   Confirm Setup shows an active authenticated link; game play remains the final proof.
6. Restart the console receiver while the devices remain paired. Confirm the input
   link repairs without pairing again and stale input releases during the gap.
7. Change one device's DHCP address, or temporarily make its saved name unavailable,
   while both remain on the same ordinary LAN. Confirm signed discovery restores both
   controller delivery and the registered-game profile without changing the saved name.
8. Disconnect and reconnect the camera. Confirm the helper declares recovery only
   after the worker receives a frame; USB enumeration alone is insufficient.
9. Upgrade both devices with the same release again. Confirm the player, center,
   reach, personalization, camera choices, Academy progress, pairing, and game registry
   remain. Keep the printed installation backup until the next play session succeeds.

Setup's **Download system report** contains versions, camera/runtime choices,
controller/profile state, and connection-check results. It contains no video,
pairing key, player calibration, ROM name, or network address, so it is the preferred
starting attachment when asking for help.

## Optional latency diagnostics

Normal installation leaves timing traces off and does not install or select the
separate diagnostic core. The [native test procedure](direction-response-benchmark.md#native-latency-and-stationary-jitter-session)
explains temporary process environments, same-architecture diagnostic builds,
private local evidence, and restoration of the normal launch configuration.
Video analysis dependencies belong in a temporary Mac environment. Capture the
physical hand and cabinet screen together; deployment alone is not a latency test.

For a guided symptom check, see [Troubleshooting by symptom](TROUBLESHOOTING.md).
