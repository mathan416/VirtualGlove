<p align="centre">
  <img src="assets/virtualglove-logo.png" alt="VirtualGlove" width="760">
</p>

# VirtualGlove

**Move your hand. Play the game.**

VirtualGlove turns hand movement and gestures into responsive RetroArch controls
using an ordinary USB camera and a **VirtualGlove Controller** built on the
Arduino UNO Q. Wear a plain glove or use your bare hand—there are no sensors,
wires, or electronics to add to it.

Move to steer. Curl fingers for buttons. Roll, push, pull, grab, throw, and punch.
VirtualGlove recognises the pose, sends authenticated controller input across
your local network, and lets RetroArch see controller input or a native
Power Glove controller.

**Current project version: 0.5.0 · Next candidate: v0.5.0-rc.1**

VirtualGlove supports RetroPie, Recalbox 10.x, Batocera 38+, and LaunchBox on
64-bit Windows. Recalbox and Batocera use **Controller Router** to combine
configured physical controllers and VirtualGlove as enabled merged Players 1–4.
RetroPie can opt into the same Router while retaining its separate-gamepad
default. LaunchBox keeps physical XInput beside VirtualGlove's managed
RetroArch controller. Every platform keeps the physical controller usable and
preserves unrelated controller settings.

On routed RetroPie, Recalbox, and Batocera, assigned physical controllers keep
their EmulationStation button mappings and player assignments in every
RetroArch/Libretro system. VirtualGlove gestures remain intentionally narrower:
ordinary joystick gestures control supported NES cores, while native Super
Glove Ball uses its separate guarded input path.

When Controller Router is enabled, a game launch always begins neutral. Physical
controllers are available immediately; VirtualGlove joins only after the hand
has returned to neutral once. This prevents a gesture observed in
EmulationStation from becoming the game's first input.

Ordinary NES games use FCEUmm. Super Glove Ball can also use the separately
named Nestopia (VirtualGlove) core for native movement and glove actions without
replacing stock Nestopia. The v0.5.0 installers provide a guarded upgrade from
v0.4.2 while preserving players, calibration, tuning, pairing, device settings,
game registrations, ROMs, saves, and controller assignments.

## Why VirtualGlove?

- **Camera-only play:** use a standard UVC camera rather than modifying a glove.
- **Two styles of NES control:** ordinary joystick output through FCEUmm and
  continuous native movement for Super Glove Ball through
  `lr-nestopia-powerglove`.
- **Original programs and game mappings:** Programs 1–14 and A–I, including
  Mattel's indexed games and documented rapid-fire exceptions.
- **Fast, direct tracking:** MediaPipe Hands processes the newest camera frame
  and sends the latest valid hand coordinate without a settling tail.
- **Family-friendly learning:** Pixel Pal guides players through 16 Glove
  Academy lessons without sending accidental input to a game.
- **Personal setup:** each player can save a hand centre, movement reach,
  joystick centre box, gesture sensitivity, and Academy progress.
- **Game-aware and safe:** registered games select their profile automatically;
  stale, lost, or unauthenticated input returns to neutral.
- **Local by design:** video stays on the Controller. Pairing and controller
  traffic are authenticated between your own devices.

![VirtualGlove Dashboard with camera and controller status](docs/images/debug-dashboard.png)

## What you need

- An Arduino UNO Q provisioned through Arduino App Lab
- A supported console: RetroPie, Recalbox 10.x, Batocera 38+, or LaunchBox with
  64-bit Windows and 64-bit RetroArch
- A UVC-compatible USB camera and powered USB hub
- A physical controller for RetroArch setup and recovery
- Both devices on the same trusted local network with internet access during
  installation
- Your own legally obtained games—VirtualGlove includes no ROMs or BIOS files

New to the hardware? Start with [Build your own](docs/BUILD_YOUR_OWN.md) for the
parts, expected cost, and difficulty.

## Install VirtualGlove

These steps install the latest stable release. Install the **same version on
both devices** and close any running RetroArch game first. The scripts
verify their downloads, ask for administrator access when needed, and preserve
existing pairing and player settings during an update.

Release-candidate testers should install `v0.5.0-rc.1` on both machines using
the pinned-version procedure in the
[technical installation reference](docs/CONFIGURATION_REFERENCE.md#versioned-multi-platform-installation).
The unversioned commands below deliberately continue to select the latest
stable release.

### 1. Prepare the Controller

Finish the UNO Q's App Lab setup, connect it to your network, and attach the
camera through the powered hub. The camera may also be connected after
installation.

### 2. Install the Controller software

Open a terminal on the UNO Q and run:

```sh
cd /home/arduino
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-uno-q.sh && bash install-uno-q.sh
```

On a first installation, the installer suggests **virtualglove** as the
Controller name, making its usual address `virtualglove.local`. Press Enter to
accept it or type a different family-friendly name. Updates preserve the
existing name.

### 3. Check the Controller

Open the Dashboard address printed by the installer—normally
`http://virtualglove.local:8088/dashboard`. The installer configures
automatic startup, the matrix display, guarded camera recovery, and its required
host helpers.

### 4. Install the console software

Choose exactly one console installer:

| Console | Run on the console | Installed in |
| --- | --- | --- |
| RetroPie | `install-retropie.sh` as the normal user | `/opt/virtualglove-src` and `/etc/virtualglove` |
| Recalbox | `install-recalbox.sh` as `root` | `/recalbox/share/system/virtualglove` |
| Batocera | `install-batocera.sh` as `root` | `/userdata/system/virtualglove` |
| LaunchBox | `install-launchbox.ps1` as the Windows player | `%LOCALAPPDATA%\VirtualGlove` |

Each Linux command downloads the latest installer from GitHub and selects the
latest stable release automatically. LaunchBox is installed from the extracted
Windows package. The complete [Installation
Guide](docs/INSTALL_README.md#3-install-the-console) has copyable commands,
prerequisites, questions, and checkpoints for all four platforms.

Run the Linux downloads from a writable persistent folder: `$HOME` on
RetroPie, `/recalbox/share/system` on Recalbox, and `/userdata/system` on
Batocera. For LaunchBox, extract the package and use `Set-Location` to enter its
`VirtualGlove` folder before running `launchbox\install-launchbox.ps1` as
Administrator.

Each installer uses the platform's persistent storage, preserves ROMs, saves,
the game registry, pairing, and unrelated controller configuration, and keeps a
physical Player 1 joypad usable beside VirtualGlove. Batocera automatically
selects the native core only for exact registered Super Glove Ball filenames
that do not already have an explicit core choice. A target without a loadable
native core still receives the complete FCEUmm joystick path.

The generic RetroPie installation exposes a separate **VirtualGlove** gamepad.
The project-maintained
[`arcade-cabinet-merger`](docs/INPUT_MODES.md#standard-retropie-and-the-virtualglove-arcade-cabinet) remains as the
development cabinet's proven reference and rollback implementation. The cabinet
now runs the shared Controller Router, which generalizes that work without
changing RetroPie's default.
Recalbox and Batocera create the enabled **VirtualGlove Merged Player 1–4**
devices and initially preserve the installer-selected Player 1 arrangement.
Setup can then assign several configured physical sources to a player and place
the single VirtualGlove on exactly one player. Original controllers remain the
only active frontend controllers. LaunchBox
keeps physical XInput plus a loopback Network RetroPad for FCEUmm games; its
real keyboard mappings remain available as a manual fallback. Native
Super Glove Ball uses only the guarded Power Glove state channel; it does not
duplicate native gestures as keyboard events.
Its installer makes **VirtualGlove RetroArch** the default NES emulator after
backing up LaunchBox's emulator and NES game definitions. Existing NES games
assigned to standard RetroArch and new NES imports use VirtualGlove automatically;
games assigned to a genuinely different emulator remain explicit overrides.

### 5. Pair the devices

Open the secure Setup address printed by the installer—normally
`https://virtualglove.local:8443/setup`—open **Connection and startup**, choose
RetroPie, Recalbox, Batocera, or LaunchBox, save the console hostname or IP address, and
continue into **Pair this Controller**. Pairing stays unavailable until the
platform and address are both saved. The guided one-time-code method is
recommended and shows only the command for the selected platform.

After confirming the browser certificate against the physical Matrix ID, the
optional **Trust this Controller** step removes future privacy warnings on that
phone or computer.

### 6. Set up a player

Choose a player, position the camera, and use **Centre hand**. Open **Glove
Academy** to learn the gestures and adjust movement reach or sensitivity only if
needed.

### 7. Play

Select **Start controller**, launch a registered game, and confirm the expected
profile. FCEUmm uses joystick mode; Super Glove Ball can also use the optional
native core selected per ROM on RetroPie, Recalbox, Batocera, or LaunchBox.

ROMs added later do not require reinstalling VirtualGlove. Refresh the console
frontend's game list, then open **Setup → Games** and register the exact ROM
filename if it is not already one of the supplied aliases. RetroPie uses its
per-ROM launch choice for native Super Glove Ball; Recalbox and Batocera apply
their exact-ROM native choice at VirtualGlove service startup; LaunchBox's
VirtualGlove RetroArch wrapper chooses the core on every launch. The complete
installation guide lists the platform-specific refresh and restart steps.

The complete [Installation Guide](docs/INSTALL_README.md) has first-install
checkpoints, illustrated pairing, camera advice, native-core setup, updates,
backups, and troubleshooting. Use it as the authoritative setup reference.

## What can you play?

VirtualGlove includes the original Programs 1–14, nine reusable cartridge
Programs A–I, plus dedicated mappings for Bad Street Brawler and Super Glove
Ball. The same recognition settings follow
the player across games; profiles change only what the recognised movements and
gestures send to the console.

| Path | What it provides |
| --- | --- |
| FCEUmm | The selected Programs 1–14 or A–I mapping, including positional movement, mapped A/B actions, and documented compound gestures. |
| Super Glove Ball with FCEUmm | A complete joystick-mode fallback that can always be selected for testing or play. |
| Super Glove Ball with Nestopia (VirtualGlove) | Continuous native X/Y and Z, Start, grab/catch, release/throw, Robo-Bullet fire, and Power Punch. The isolated core is supported on RetroPie, Recalbox, Batocera, and LaunchBox; FCEUmm remains the fallback. |

Rapid A/B defaults on only where an individual program description explicitly
identifies a pulsed button: Program 7 A, Program B A, Program H A/B, and Bad
Street Brawler B. Every other profile defaults off. The registered Blaster
Master, Double Dribble, Racket Attack, Ice Hockey, and Alpha Mission entries
retain Mattel's documented off instructions. Programs 13 and 14 also support
deliberate physical-controller and gestures-off play.

Dashboard Rapid A/B switches control button repetition only; profile-owned fast
turns, pulsed movement, turbo movement, and compound actions retain their own
timing. Saved per-game overrides survive upgrades. Choose **Use profile
defaults** while that game is running to remove its overrides and adopt the
corrected defaults.

The [Gameplay Guide](docs/GAMEPLAY_GUIDE.md#program-cards-1-14) shows every
numeric Program gesture, compound action, release rule, indexed game, exception,
objective, and practice challenge. The
[VirtualGlove Input Modes](docs/INPUT_MODES.md) explains why the joystick and
native emulator paths feel different and how physical Player 1 controls join
each platform.

The numeric Program section includes gesture-by-gesture controls, compound
action timing, the complete official game index, and the five automatic
rapid-fire exceptions. Program 13 is the mixed physical-controller option;
Program 14 deliberately turns camera gestures off for the active game.

## How it works

![End-to-end VirtualGlove flow from camera to game](docs/images/architecture/end-to-end.png)

1. The camera delivers its newest frame to the VirtualGlove Controller.
2. MediaPipe Hands finds the palm, wrist, and finger landmarks.
3. Shared recognition turns those landmarks into position, fingers, rolls,
   depth motion, and menu poses.
4. The Controller sends the newest authenticated state to the selected console.
5. The console publishes either Player 1 input or native glove state for the
   selected emulator core.

Pairing is tied to a private shared key rather than one permanent IP address.
If DHCP changes an address or `.local` resolution temporarily fails, the paired
devices can rediscover one another on the local network without broadcasting
controller states or requiring a new pairing.

## Meet Pixel Pal

Pixel Pal helps players learn, personalise, test, and troubleshoot without
turning setup into an engineering exercise.

- **Glove Academy** teaches all 16 movements and gestures while game output is
  paused.
- **Tune gestures** records guided examples and previews a conservative
  adjustment before saving it.
- **Find the best camera settings** compares only choices supported by the
  attached camera and changes nothing until the player accepts a recommendation.
- **Rock Paper Scissors** provides a camera-controlled practice game that does
  not require a connected console.

## Controller pages

| Page | Purpose |
| --- | --- |
| Dashboard · `/dashboard` | See live controls and set per-game A/B rapid fire. |
| Play · `/play` | Challenge Pixel Pal to Rock Paper Scissors. |
| Glove Academy · `/learn` | Learn gestures, set movement reach, and personalise recognition safely. |
| Setup · `/setup` | Manage players, camera choices, console pairing, games, backups, and display preferences. |
| Help · `/help` | Read the complete manuals and printable PDFs directly on the Controller. |

## Documentation

### Start here

| You want to… | Read… |
| --- | --- |
| Install, pair, and play your first game | [Installation Guide](docs/INSTALL_README.md) |
| Learn gestures, Programs, and game controls | [Gameplay Guide](docs/GAMEPLAY_GUIDE.md) |
| Understand joystick, merged-controller, and native modes | [VirtualGlove Input Modes](docs/INPUT_MODES.md) |
| Choose or troubleshoot a camera | [Camera Guide](docs/CAMERA_GUIDE.md) |
| Assemble a printed case quickly | [Enclosure Assembly Quick Reference](docs/ENCLOSURE_QUICK_REFERENCE.md) |
| Print or customise a case | [Controller Enclosure Guide](docs/ENCLOSURE_GUIDE.md) |
| Recognise matrix animations and messages | [Matrix Display Guide](docs/MATRIX_GUIDE.md) |
| Find a quick command or status reminder | [Quick Reference](docs/cheatsheet.md) |
| Solve a problem by symptom | [Troubleshooting](docs/TROUBLESHOOTING.md) |

### Go deeper

| You want to… | Read… |
| --- | --- |
| See the current components and data flow | [Architecture](docs/ARCHITECTURE.md) |
| Look up every setting and command | [Configuration Reference](docs/CONFIGURATION_REFERENCE.md) |
| Follow the engineering process, experiments, and movement validation | [Engineering Journey](docs/ENGINEERING_JOURNEY.md) |
| Repeat camera, latency, trace, or native research | [Engineering Toolkit](docs/ENGINEERING_TOOLKIT.md) |
| Review ROM-level native and joystick evidence | [Power Glove Game ROM Input Audit](docs/power-glove-rom-input-audit.md) |
| Review security and pairing boundaries | [Security Policy](docs/SECURITY.md) |
| Check dependencies and third-party terms | [Third-party Notices](THIRD_PARTY_NOTICES.md) |
| Contribute code or documentation | [Contributing Guide](docs/CONTRIBUTING.md) |

Printable editions of all maintained guides are available in
[`output/pdf/`](output/pdf/). The Controller serves the same documentation from
its local Help page.

The public website is maintained with the application under [`website/`](website/).
Its dependency-free builder reads `config/release.json`, renders four static
pages, validates release-sensitive links and commands, and creates
`output/website/VirtualGlove-Website.zip` for manual upload.

## Project status

VirtualGlove 0.5.0 keeps the proven CPU MediaPipe Hands path, Programs 1-14,
live dead-zone visualization, and source-accurate
rapid-fire behaviour. It extends the authenticated console integration to
Recalbox, Batocera, and LaunchBox while retaining RetroPie.

The `v0.5.0-rc.1` candidate has completed physical controller and VirtualGlove
acceptance on RetroPie, Recalbox 10.1.1, Batocera 43.1, and LaunchBox. This
includes ordinary NES play, native Super Glove Ball, physical-controller
coexistence, hotkeys, reboot persistence, and Controller Router remapping.
Recalbox's all-Libretro physical path has also been exercised with Game Boy,
ColecoVision, and Game Gear games.

Recalbox and Batocera use Controller Router to publish enabled merged Players
1–4 from configured physical sources and at most one VirtualGlove. Standard
RetroPie keeps its separate gamepad until Router is explicitly enabled; the
project arcade cabinet now uses Router for its two I-PAC interfaces, 8BitDo
controllers, and VirtualGlove.
LaunchBox uses a local RetroPad while leaving XInput and
real keyboard controls available. Every platform supports registered FCEUmm
games and the separately named Nestopia (VirtualGlove) path for native Super
Glove Ball. The installers update managed files while preserving pairing,
players, calibration, tuning, Academy progress, games, ROMs, and saves.

Use Setup's **Download system report** when asking for help. It records useful
software, camera, controller, and connection health without including video,
pairing keys, player calibration, ROM names, or network addresses.

## Contributing and licensing

Issues, careful test reports, documentation improvements, and code contributions
are welcome. Please read the [Contributing Guide](docs/CONTRIBUTING.md) before
opening a change. Release history is kept in the [Changelog](docs/CHANGELOG.md).

VirtualGlove is maintained by **Iain Bennett** and is licensed under the
[MIT License](LICENSE). The modified Nestopia core is GPLv2 software and remains
separate from the MIT application. Nintendo, NES, Power Glove, and the named
games belong to their respective owners. See
[Third-party Notices](THIRD_PARTY_NOTICES.md) for dependency, model, asset, and
native-core licensing details.
