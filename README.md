<p align="center">
  <img src="assets/virtualglove-logo.png" alt="VirtualGlove" width="760">
</p>

# VirtualGlove

**Move your hand. Play the game.**

VirtualGlove turns hand movement and gestures into responsive RetroPie controls
using an ordinary USB camera and a **VirtualGlove Controller** built on the
Arduino UNO Q. Wear a plain glove or use your bare hand—there are no sensors,
wires, or electronics to add to it.

Move to steer. Curl fingers for buttons. Roll, push, pull, grab, throw, and punch.
VirtualGlove recognizes the pose, sends authenticated controller input across
your local network, and lets RetroArch see a virtual gamepad or a native
Power Glove controller.

**Current project version: 0.4.1 · Next candidate: v0.4.1-rc.1**

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
- A Raspberry Pi with a working RetroPie installation
- A UVC-compatible USB camera and powered USB hub
- A physical controller for RetroArch setup and recovery
- Both devices on the same trusted local network with internet access during
  installation
- Your own legally obtained games—VirtualGlove includes no ROMs or BIOS files

New to the hardware? Start with [Build your own](docs/BUILD_YOUR_OWN.md) for the
parts, expected cost, and difficulty.

## Install VirtualGlove

These steps install the current public release candidate. Install the **same
version on both devices** and close any running RetroArch game first. The scripts
verify their downloads, ask for administrator access when needed, and preserve
existing pairing and player settings during an update.

### 1. Prepare the Controller

Finish the UNO Q's App Lab setup, connect it to your network, and attach the
camera through the powered hub. The camera may also be connected after
installation.

### 2. Install the Controller software

Open a terminal on the UNO Q and run:

```sh
cd /home/arduino
curl -fLO \
  https://github.com/mathan416/VirtualGlove/releases/download/v0.4.1-rc.1/install-uno-q.sh
bash install-uno-q.sh --development v0.4.1-rc.1
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

### 4. Install the RetroPie software

Open a terminal on the Raspberry Pi and run:

```sh
curl -fLO \
  https://github.com/mathan416/VirtualGlove/releases/download/v0.4.1-rc.1/install-retropie.sh
bash install-retropie.sh --development v0.4.1-rc.1
```

If an older Buster-based RetroPie reports that its Raspbian repository has no
Release file, stop and follow [Buster package source moved](docs/TROUBLESHOOTING.md#buster-package-source-moved),
then rerun this step. The installer does not silently rewrite operating-system
repositories.

### 5. Pair the devices

Open the secure Setup address printed by the installer—normally
`https://virtualglove.local:8443/setup`—open **Connect to RetroPie**, save the
RetroPie address, and continue into **Pair this Controller**. The guided
one-time-code method is recommended.
For an optional, resumable first-game walkthrough, select **Get ready to play**
on Setup or Dashboard. It checks your player, connection, camera, center, and
essential gestures in safe practice before you explicitly enable game controls.

After confirming the browser certificate against the physical Matrix ID, the
optional **Trust this Controller** step removes future privacy warnings on that
phone or computer.

### 6. Set up a player

Choose a player, position the camera, and use **Center hand**. Open **Glove
Academy** to learn the gestures and adjust movement reach or sensitivity only if
needed.

### 7. Play

Select **Start controller**, launch a registered game, and confirm the expected
profile. FCEUmm uses joystick mode; Super Glove Ball can also use the optional
native core selected from RetroPie's per-ROM launch menu.

The complete [Installation Guide](docs/INSTALL_README.md) has first-install
checkpoints, illustrated pairing, camera advice, native-core setup, updates,
backups, and troubleshooting. Use it as the authoritative setup reference.

## What can you play?

VirtualGlove includes the original Programs 1–14, nine reusable cartridge
Programs A–I, plus dedicated mappings for Bad Street Brawler and Super Glove
Ball. The same recognition settings follow
the player across games; profiles change only what the recognized movements and
gestures send to the console.

| Path | What it provides |
| --- | --- |
| FCEUmm | The selected Program 1–14 or A–I mapping, including positional movement, mapped A/B actions, and documented compound gestures. |
| Super Glove Ball with FCEUmm | A complete joystick-mode fallback that can always be selected for testing or play. |
| Super Glove Ball with `lr-nestopia-powerglove` | Continuous native X/Y and Z, Start, grab/catch, release/throw, Robo-Bullet fire, and Power Punch. |

The [Gameplay Guide](docs/GAMEPLAY_GUIDE.md) shows every gesture, Program, game
mapping, objective, and practice challenge. The
[Native Emulation guide](docs/NATIVE_EMULATION_EXPLAINED.md) explains why the
two emulator paths feel different.

## How it works

![End-to-end VirtualGlove flow from camera to game](docs/images/architecture/end-to-end.png)

1. The camera delivers its newest frame to the VirtualGlove Controller.
2. MediaPipe Hands finds the palm, wrist, and finger landmarks.
3. Shared recognition turns those landmarks into position, fingers, rolls,
   depth motion, and menu poses.
4. The Controller sends the newest authenticated state to RetroPie.
5. RetroPie publishes either virtual gamepad input or native glove state for
   the selected emulator core.

Pairing is tied to a private shared key rather than one permanent IP address.
If DHCP changes an address or `.local` resolution temporarily fails, the paired
devices can rediscover one another on the local network without broadcasting
controller states or requiring a new pairing.

## Meet Pixel Pal

Pixel Pal helps players learn, personalize, test, and troubleshoot without
turning setup into an engineering exercise.

- **Glove Academy** teaches all 16 movements and gestures while game output is
  paused.
- **Tune gestures** records guided examples and previews a conservative
  adjustment before saving it.
- **Find the best camera settings** compares only choices supported by the
  attached camera and changes nothing until the player accepts a recommendation.
- **Rock Paper Scissors** provides a camera-controlled practice game that does
  not require RetroPie.

## Controller pages

| Page | Purpose |
| --- | --- |
| Dashboard · `/dashboard` | See the camera, selected game profile, tracking state, and generated controls. |
| Play · `/play` | Challenge Pixel Pal to Rock Paper Scissors. |
| Glove Academy · `/learn` | Learn gestures, set movement reach, and personalize recognition safely. |
| Setup · `/setup` | Manage players, camera choices, console pairing, games, backups, and display preferences. |
| Help · `/help` | Read the complete manuals and printable PDFs directly on the Controller. |

## Documentation

### Start here

| You want to… | Read… |
| --- | --- |
| Install, pair, and play your first game | [Installation Guide](docs/INSTALL_README.md) |
| Learn gestures, Programs, and game controls | [Gameplay Guide](docs/GAMEPLAY_GUIDE.md) |
| Choose or troubleshoot a camera | [Camera Guide](docs/CAMERA_GUIDE.md) |
| Recognize matrix animations and messages | [Matrix Display Guide](docs/MATRIX_GUIDE.md) |
| Find a quick command or status reminder | [Quick Reference](docs/cheatsheet.md) |
| Solve a problem by symptom | [Troubleshooting](docs/TROUBLESHOOTING.md) |

### Go deeper

| You want to… | Read… |
| --- | --- |
| See the current components and data flow | [Architecture](docs/ARCHITECTURE.md) |
| Understand joystick and native emulation | [Native Emulation Explained](docs/NATIVE_EMULATION_EXPLAINED.md) |
| Review proven Super Glove Ball behavior | [Native Compatibility Record](docs/super-glove-ball-native.md) |
| Look up every setting and command | [Configuration Reference](docs/CONFIGURATION_REFERENCE.md) |
| Follow the one-week engineering process and experiments | [Engineering Journey](docs/ENGINEERING_JOURNEY.md) |
| Review security and pairing boundaries | [Security Policy](docs/SECURITY.md) |
| Check dependencies and third-party terms | [Third-party Notices](THIRD_PARTY_NOTICES.md) |
| Contribute code or documentation | [Contributing Guide](docs/CONTRIBUTING.md) |

Printable editions of all maintained guides are available in
[`output/pdf/`](output/pdf/). The Controller serves the same documentation from
its local Help page.

## Project status

Version 0.4.1 keeps the proven CPU MediaPipe Hands path and adds the complete
Programs 1–14 catalog, guided readiness checks, live dead-zone visualization,
and one-way migration to `virtualglove-*` runtime names. The candidate updates
the UNO Q and RetroPie together while preserving pairing, players, calibration,
tuning, Academy progress, and the installed game registry. Different cameras,
rooms, players, controllers, and Raspberry Pi installations remain valuable
real-world tests.

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
