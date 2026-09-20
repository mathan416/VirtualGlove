# Installation and Setup

This guide takes you from a prepared Arduino UNO Q and game system to your
first working VirtualGlove game. You will install VirtualGlove on both devices,
pair them securely, center your hand, and test the controls.

VirtualGlove 0.5.0 supports RetroPie, Recalbox, Batocera, and LaunchBox on
Windows. The normal commands below install the latest stable release. If you
need a specific version or a development build, use the
[technical installation reference](CONFIGURATION_REFERENCE.md#versioned-multi-platform-installation).

The next release candidate is `v0.5.0-rc.1`. After it is published, install
that exact version on both machines with the pinned-version procedure in the
technical reference. The unversioned commands in this guide intentionally
continue to select the latest stable release.

## 1. Before you begin

You need:

- a provisioned **VirtualGlove Controller** running on an Arduino UNO Q;
- a UVC USB camera connected through a powered USB hub;
- a supported game system: RetroPie, Recalbox, Batocera, or LaunchBox;
- a physical controller already working with that game system;
- both devices on the same trusted local network with internet access; and
- your own legally obtained NES games. VirtualGlove includes no ROMs or BIOS files.

Close RetroArch and any running game before installation. Keep both devices
powered and connected while the installers run. First installation can take
several minutes.

### Choose your console section

| Platform | Where you install | How Player 1 works |
| --- | --- | --- |
| RetroPie | Raspberry Pi terminal | VirtualGlove normally appears beside your physical controller. Optional Controller Router can combine and assign physical controllers and VirtualGlove. |
| Recalbox 10.x | Recalbox terminal as `root` | Controller Router initially preserves your selected physical controller and VirtualGlove as merged Player 1; Setup can later assign Players 1–4. |
| Batocera 38 or newer | Batocera terminal as `root` | Controller Router initially preserves your selected physical controller and VirtualGlove as merged Player 1; Setup can later assign Players 1–4. |
| LaunchBox | Windows PowerShell | Your physical XInput controller remains available while VirtualGlove supplies a managed RetroArch controller. |

Ordinary NES games can use FCEUmm or the platform's stock Nestopia core. Super Glove Ball also supports the
special **Nestopia (VirtualGlove)** core, which provides its native three-axis
movement and glove actions. FCEUmm remains a complete joystick-mode fallback.

### Optional Controller Router

After pairing, Setup shows **Controller Router**. It lists only controllers
already configured by EmulationStation. Review the suggested Player 1–4 choices,
choose one player or Unassigned for each physical controller, choose at most one
VirtualGlove player, then save. Opening the card never changes the console.
Newly configured EmulationStation controllers appear automatically as
**Unassigned**. If you remap an assigned controller in EmulationStation, Router
keeps its player assignment and uses the validated new mapping on the next game
launch; Setup marks it **Mapping refreshed**.

Recalbox and Batocera automatically carry their released Player 1 selection into
the new format. A normal RetroPie install keeps its separate `VirtualGlove`
gamepad until Router is explicitly saved and applied. Original physical
controllers remain the frontend controllers; merged outputs stay neutral in
EmulationStation and become active during Libretro gameplay.

| Input | Where it works after Router is enabled |
| --- | --- |
| Assigned physical controllers | Their selected merged Player 1-4 slot in any RetroArch/Libretro game. Several physical controllers may share one player. |
| VirtualGlove joystick gestures | Its selected player in supported FCEUmm and stock Nestopia NES games. |
| VirtualGlove native gestures | Super Glove Ball in Nestopia (VirtualGlove), through the separate native-input path. |
| Original physical controllers | Console menus and EmulationStation. Router temporarily takes ownership during Libretro gameplay to prevent doubled input. |
| Standalone, non-Libretro emulators | Not managed by Controller Router. They retain the platform's normal controller setup. |

Assigning a physical controller in Router does not reconfigure its buttons.
Router uses the mapping already saved by EmulationStation and adopts a valid
later remap at the next game launch. Player 1 is special: only a physical
controller assigned to Player 1 carries the platform's menu and exit hotkey.
VirtualGlove Select never becomes a hotkey.

At each Libretro game launch, physical controllers work immediately. Router
discards any glove state seen in the frontend. In a game that accepts
VirtualGlove gestures, rest the hand at neutral once; VirtualGlove then joins
the selected merged player. This startup handshake prevents a held frontend
gesture from becoming an accidental first game input.

Use **Check controllers** and press a direction or button on each pad during the
ten-second test. The result names each responding or unavailable controller,
shows its stable identity suffix and assigned player, and keeps an unavailable
warning visible even when another pad responds. Close any running RetroArch
game before changing assignments. **Restore previous assignments** provides an
atomic rollback after a save.

The same assignments can be managed locally without pairing. Open the console
terminal and run the platform's persistent command:

- RetroPie: `sudo /opt/virtualglove/bin/virtualglove-controller-router setup`
- Recalbox: `sh /recalbox/share/system/virtualglove/scripts/virtualglove-controller-router setup`
- Batocera: `sh /userdata/system/virtualglove/scripts/virtualglove-controller-router setup`

The terminal screen detects the platform, shows controller connection state,
tests live controls, assigns Players 1–4, and provides save and rollback actions.
This local tool changes controller assignments only; secure
Controller-to-console pairing remains a separate Setup step.

### Open a Controller terminal

For a new UNO Q, first complete Arduino App Lab setup and connect it to your
network. App Lab shows its current name or IP address. From another computer,
open a terminal and connect with:

```sh
ssh arduino@UNO-Q-NAME.local
```

Use the password you created during board setup. The installer may request it
again when administrator access is needed, but it does not save the password.

## 2. Install the VirtualGlove Controller

In the UNO Q terminal, copy and run these two lines:

```sh
cd /home/arduino
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-uno-q.sh && bash install-uno-q.sh
```

The installer verifies the release, installs VirtualGlove, loads the matching
Matrix firmware, and configures automatic startup. It also installs the guarded
camera-recovery and shutdown helpers used by the Controller.

### Questions the installer asks

On a first installation, the installer shows the UNO Q's current name and
suggests **virtualglove**. Press Enter to use `virtualglove.local`, or enter a
different short name such as `games-room`. Confirm the displayed address before
continuing. Updates keep the established name and do not ask again.

The camera can be connected before or after installation. Camera recovery is
configured automatically when a supported camera is available.

### What is preserved

Rerunning the installer updates VirtualGlove without erasing players,
calibration, gesture tuning, dead-zone settings, camera choices, pairing, or
device configuration. The installer prints the location of any backup it
creates.

### Controller checkpoint

Open the Dashboard address printed by the installer, normally:

`http://virtualglove.local:8088/dashboard`

The Dashboard should load. With gestures off, a closed camera is normal. Open
**Play** or **Glove Academy** to confirm that the camera can show your whole
hand, then return to Dashboard with controller output stopped.

For the simplest first setup, leave **Camera**, frame rate, exposure, and camera
reader on their recommended automatic settings. If tracking is delayed or
unstable, use **Find the best camera settings** in Setup. The
[Camera Guide](CAMERA_GUIDE.md) explains the advanced choices.

![Advanced camera settings with Automatic, a discovered camera, and optional manual exposure](images/setup-camera.png)

## 3. Install the console

Choose only the section for your game system. Close RetroArch first. On a new
installation, the console installer asks for the Controller name or IP address;
enter the name selected above, normally `virtualglove.local`.

Each section uses the same latest-release installer as future updates. The
installer preserves ROMs, saves, pairing, game registrations, and unrelated
controller settings.

### RetroPie

#### Before you start

Confirm that a physical controller works in EmulationStation and that RetroPie
has internet access. Connect to RetroPie as its normal user, without starting a
root shell.

#### Install

Run this command in the RetroPie terminal:

```sh
cd "$HOME"
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-retropie.sh && bash install-retropie.sh
```

#### Questions the installer asks

- Enter the Controller name or address on a first installation.
- If a required emulator is missing, the installer offers to add it through
  RetroPie Setup.
- If Super Glove Ball is registered, the installer can add the optional
  `lr-nestopia-powerglove` core packaged for RetroArch's actual processor ABI.
  It verifies and load-checks the core first; declining or an incompatible core
  leaves FCEUmm available.
- The optional **VirtualGlove Calibration Test** can be added to the Ports menu
  now or on a later installer run.

If an older Buster-based RetroPie reports that its Raspbian repository has no
Release file, stop and follow
[Buster package source moved](TROUBLESHOOTING.md#buster-package-source-moved),
then run the installer again.

#### What the installer configures

VirtualGlove appears as a separate game controller. Your physical controller
remains available for menus and gameplay. Registered games tell VirtualGlove
which profile to use, and game exit safely releases all controls.

The VirtualGlove development arcade cabinet uses optional Controller Router to
combine its two I-PAC interfaces, supported 8BitDo controllers, and
VirtualGlove into shared arcade-player devices. Its original cabinet merger is
retained as a tested rollback reference, but is no longer the active path.
Router is not enabled by the normal RetroPie installer. Most RetroPie systems
should keep the separate-controller arrangement above. See [VirtualGlove Input
Modes](INPUT_MODES.md#standard-retropie-and-the-virtualglove-arcade-cabinet)
for the two designs and when each is appropriate.

For Super Glove Ball, FCEUmm is the safe fallback. To use native glove control,
choose `lr-nestopia-powerglove` for that ROM from RetroPie's launch menu.

#### Checkpoint

The final report should confirm that the receiver starts automatically. It is
normal to see `ACTION` for pairing or physical gameplay checks that still need
you.

#### First game and updates

After pairing, test an ordinary registered game with FCEUmm. If Router is
enabled, confirm the physical controller works immediately, rest the hand at
neutral once, and then confirm VirtualGlove works without stopping or restarting
it. Test Super Glove Ball separately
if you installed its native core. To update later, close the game and rerun the
same install command.

<!-- PAGEBREAK -->

### Recalbox 10.x

#### Before you start

Confirm that your intended physical Player 1 controller works in
EmulationStation. Connect to Recalbox over SSH as `root`; do not add `sudo` to
the commands below.

#### Install

Run this command in the Recalbox terminal:

```sh
cd /recalbox/share/system
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-recalbox.sh && bash install-recalbox.sh
```

#### Questions the installer asks

- Enter the Controller name or address on a first installation.
- If exactly one configured controller is available, it is selected as physical
  Player 1 automatically.
- If several controllers are available, choose the one you want VirtualGlove
  to share with. The installer displays the available choices.

#### What the installer configures

Recalbox initially enables **VirtualGlove Merged Player 1**, preserving the
selected physical controller and VirtualGlove arrangement. After pairing, the
**Controller Router** card in Setup can enable merged Players 1–4, assign
several configured physical controllers to one player, or move the one
VirtualGlove to another player. Original controllers continue to operate
EmulationStation without duplicate menu movement. During any Libretro game,
assigned physical controllers use the merged players. VirtualGlove gestures
join only compatible NES joystick games or the separate native Super Glove
Ball path. Unrelated settings are preserved.

Registered Super Glove Ball filenames use the packaged Nestopia (VirtualGlove)
core when a compatible core is available and you have not already made an
explicit per-game choice. FCEUmm remains available if the native core cannot be
used.

#### Checkpoint

The final report should confirm automatic startup, the initial physical Player
1 controller, and the Controller Router output. Pairing, extra player
assignments, and live gameplay may still appear as `ACTION` items.

#### First game and updates

After pairing, test an ordinary registered game with FCEUmm. Confirm that hand
controls and the physical controller both operate Player 1. Then test one
non-NES Libretro game with the physical controller; VirtualGlove gestures are
not expected in that game. Finally, test Super Glove Ball if it is installed.
To update later, close the game and rerun the same install command.

<!-- PAGEBREAK -->

### Batocera 38 and newer

#### Before you start

Confirm that your intended physical Player 1 controller works in
EmulationStation. Connect to Batocera over SSH as `root`; do not add `sudo` to
the commands below.

#### Install

Run this command in the Batocera terminal:

```sh
cd /userdata/system
curl -fLO https://github.com/mathan416/VirtualGlove/releases/latest/download/install-batocera.sh && bash install-batocera.sh
```

#### Questions the installer asks

- Enter the Controller name or address on a first installation.
- If exactly one configured controller is available, it is selected as physical
  Player 1 automatically.
- If several controllers are available, choose the one you want VirtualGlove
  to share with. The installer displays the available choices.

#### What the installer configures

Batocera initially enables **VirtualGlove Merged Player 1**, preserving the
selected physical controller and VirtualGlove arrangement. After pairing, the
**Controller Router** card in Setup can enable merged Players 1–4, assign
several configured physical controllers to one player, or move the one
VirtualGlove to another player. Original controllers continue to operate
EmulationStation without duplicate menu movement. During any Libretro game,
assigned physical controllers use the merged players. VirtualGlove gestures
join only compatible NES joystick games or the separate native Super Glove
Ball path. Unrelated settings are preserved.

Registered Super Glove Ball filenames use the packaged Nestopia (VirtualGlove)
core when a compatible core is available and you have not already made an
explicit per-game choice. FCEUmm remains available if the native core cannot be
used.

#### Checkpoint

The final report should confirm automatic startup, the initial physical Player
1 controller, and the Controller Router output. Pairing, extra player
assignments, and live gameplay may still appear as `ACTION` items.

#### First game and updates

After pairing, test an ordinary registered game with FCEUmm. Confirm that hand
controls and the physical controller both operate Player 1. Then test one
non-NES Libretro game with the physical controller; VirtualGlove gestures are
not expected in that game. Finally, test Super Glove Ball if it is installed.
To update later, close the game and rerun the same install command.

<!-- PAGEBREAK -->

### LaunchBox on Windows x86-64

#### Before you start

Install 64-bit Python with its `py` launcher and 64-bit RetroArch with FCEUmm.
Confirm that your physical XInput controller works in RetroArch. Close
LaunchBox, Big Box, and RetroArch before installation.

Download `VirtualGlove-LaunchBox.zip` from the latest VirtualGlove release and
extract it to a temporary folder. The archive contains a folder named
`VirtualGlove`. Open PowerShell as Administrator, using the same Windows
account that runs LaunchBox.

#### Install

Move into the extracted `VirtualGlove` folder, then run the installer. Replace
the example extraction, LaunchBox, RetroArch, and Controller locations with
the locations on your computer:

```powershell
Set-Location "$env:USERPROFILE\Downloads\VirtualGlove"
powershell -ExecutionPolicy Bypass -File .\launchbox\install-launchbox.ps1 `
  -LaunchBoxRoot "C:\LaunchBox" -RetroArchRoot "C:\RetroArch" `
  -ControllerHost "virtualglove.local"
```

Change the two folders and Controller name to match your system.

#### Questions the installer asks

- Confirm the LaunchBox and RetroArch folders if your installation uses
  different locations.
- Allow the authenticated VirtualGlove receiver on Private networks if Windows
  asks. Do not enable it for Public networks.

#### What the installer configures

LaunchBox gains a **VirtualGlove RetroArch** emulator for NES games. Ordinary
games use FCEUmm with VirtualGlove's managed RetroArch controller. Your physical
XInput controller and real keyboard remain available. Super Glove Ball uses
Nestopia (VirtualGlove) when its exact filename is registered.

Existing NES games assigned to standard RetroArch are moved to VirtualGlove
RetroArch. Games explicitly assigned to another emulator remain unchanged.
ROMs, saves, pairing, and unrelated LaunchBox settings are preserved.

#### Checkpoint

The installer should confirm the VirtualGlove RetroArch entry and its managed
receiver. LaunchBox does not have a separate check-only command, so the first
registered game is the final test.

#### First game and updates

After pairing, launch an ordinary registered game from LaunchBox. Confirm that
VirtualGlove directions and buttons work while the physical XInput controller
still controls Player 1. Test Super Glove Ball separately. To update later,
close LaunchBox, Big Box, and RetroArch, extract the new package, and rerun the
same installer.

<!-- PAGEBREAK -->

### Add NES ROMs after VirtualGlove is installed

Adding a ROM does not require reinstalling VirtualGlove:

1. Copy or import the `.nes`, `.zip`, or `.7z` game and refresh the platform's
   game list.
2. Open **Setup -> Games** on the Controller. Add the exact filename and choose
   its profile if it is not already listed, then select **Validate** and
   **Save**. Matching is exact and case-insensitive, and includes the extension.
3. Follow the platform note below.

| Platform | After adding the ROM |
| --- | --- |
| RetroPie | Copy games into `~/RetroPie/roms/nes` and restart EmulationStation or refresh its game list. Select `lr-nestopia-powerglove` from the per-ROM launch menu only when you want native Super Glove Ball. |
| Recalbox | Copy games into `/recalbox/share/roms/nes` and update the game list. Restart the VirtualGlove service or reboot after registering Super Glove Ball so its automatic core choice is refreshed. |
| Batocera | Copy games into `/userdata/roms/nes` and update the game list. Restart the VirtualGlove service or reboot after registering Super Glove Ball so its automatic core choice is refreshed. |
| LaunchBox | Import the game into **Nintendo Entertainment System**. New games inherit **VirtualGlove RetroArch**. The launcher checks the registry on every start, so no service restart is needed. |

An existing explicit per-game emulator choice is preserved. Registering a game
changes only VirtualGlove's profile and launch behavior; it does not copy,
rename, or modify the ROM.

<!-- PAGEBREAK -->

## 4. Pair the devices

Pairing securely gives the Controller and console the same private credential.
It does not start controller output.

1. Open the secure Setup address, normally
   `https://virtualglove.local:8443/setup`. A first visit may show a privacy
   warning because the Controller is a private local device.
2. Under **Connection and startup**, choose RetroPie, Recalbox, Batocera, or
   LaunchBox. Enter the console hostname or IP address, then select
   **Save connection**. Pairing stays unavailable until both fields are saved.
3. Select **Check console address**. This confirms that the saved name or address
   can be reached; you can run the check again whenever needed.
4. Under **Pair this Controller**, choose **One-time code (recommended)** and
   select **Continue**.
5. Compare the Matrix `ID` with the beginning of the browser certificate's
   SHA-256 fingerprint. If they differ, stop. If they match, confirm the match,
   enter the six-digit Matrix approval PIN, and continue.
6. Run the one-time pairing command shown by Setup on the selected console.
   Enter its 20-character code in the browser within five minutes, then select
   **Pair with console**.
7. Wait for **Pairing complete**. This confirms an authenticated connection; a
   game test is still required.

![Guided pairing starts with the saved console and a choice of one-time code or SSH password.](images/setup-pairing-method.png)

![Controller confirmation with certificate comparison, matrix approval PIN, and remaining time.](images/setup-pairing-confirm.png)

![Pairing in progress while the request waits for the selected console.](images/setup-pairing-progress.png)

![Pairing complete, with the next step on Dashboard.](images/setup-pairing-complete.png)

The confirmation window lasts two minutes. If it expires or pairing fails,
select **Start a new confirmation** and obtain a new console code.

### Optional: pair with your console password

RetroPie, Recalbox, and Batocera can instead use **SSH password** in the pairing
card. Complete the same certificate and Matrix PIN checks, then enter the
console's SSH username and password. The Controller uses the password only for
that attempt and does not save it.

LaunchBox uses one-time-code pairing only and never requests a Windows password.
If neither method works, see
[Pairing and token management](CONFIGURATION_REFERENCE.md#pairing-and-token-management).

### Optional: trust the Controller certificate

After confirming that the Matrix ID matches the browser certificate, Setup can
download a trust certificate for that phone or computer. Installing it removes
future privacy warnings. Never install it if the IDs do not match.

## 5. Calibrate and test a game

### Center your hand

1. Open Dashboard and choose the correct player.
2. Position the camera so your whole hand remains visible throughout the area
   where you intend to move.
3. Hold a relaxed open hand at a comfortable center and distance.
4. Select **Center hand** and remain still until it reports completion.

Center again after moving the camera, changing playing position, or switching
to a player who has not been calibrated. The saved center belongs to the player
and does not chase the hand during play.

### Test an ordinary game

1. On Dashboard, select **Start controller**.
2. Launch a registered NES game that uses FCEUmm.
3. Confirm the expected profile appears on Dashboard and the Matrix.
4. Test Left, Right, Up, Down, A, B, Start, and Select.
5. Confirm the physical controller still works for Player 1.
6. Return the hand to center and confirm movement stops.
7. Exit the game and confirm gesture output stops.

If Controller Router is enabled, also test every assigned physical controller.
On Recalbox and Batocera, or a routed RetroPie system, launch a non-NES Libretro
game and confirm the physical assignments still work. This proves the Router's
all-Libretro physical path. It does not mean VirtualGlove gestures are expected
outside their supported NES and native Super Glove Ball paths.

Different Programs deliberately use different gestures. If a control does not
behave as expected, check the selected Program in the
[Gameplay Guide](GAMEPLAY_GUIDE.md) before changing calibration.

**Checkpoint:** A gesture must change the intended control inside the running
game. A running service or visible controller name alone is not an end-to-end
test.

### Test Super Glove Ball

- With FCEUmm, test the ordinary joystick profile first.
- With Nestopia (VirtualGlove), test Start, hand movement, forward and backward
  depth, grab and throw, index-point fire, and Power Punch.
- On RetroPie, choose the native core from the ROM's launch menu. Recalbox,
  Batocera, and LaunchBox select it automatically for an exact registered ROM
  unless you have made another explicit choice.

If the native core is unavailable or unsuitable, return that ROM to FCEUmm;
the rest of VirtualGlove remains installed.

## 6. Confirm startup and finish

1. Reboot the Controller and console normally.
2. Confirm that Dashboard returns and the console reconnects without pairing
   again.
3. Confirm the selected player, center, tuning, camera choices, and game
   registrations remain available.
4. Launch the ordinary FCEUmm test game again and confirm both VirtualGlove and
   the physical controller work.
5. If installed, test Super Glove Ball again.

The Controller remembers whether you selected **Start controller** or **Stop
controller**, but controls are delivered only during a recognized game session
or an intentional manual profile. Unknown games and game exit release all
controls safely.

## Updates and checks

To update, close running games and repeat the same install command on the
Controller and console. Use the same release on both devices. The installers
stop managed VirtualGlove processes before replacing application files and
preserve private settings and user data.

### Fresh installation checklist

1. Install the Controller from `/home/arduino`, then open its printed Dashboard
   address.
2. Confirm a physical controller already works on the console before installing
   its VirtualGlove integration.
3. Install the same VirtualGlove release on the selected console platform.
4. Save the platform and console address in Setup, check the address, and pair
   the two devices.
5. Center the selected player and test one ordinary registered NES game with
   both VirtualGlove and the physical controller.
6. If installed, test native Super Glove Ball separately, then reboot both
   devices and repeat the game and exit checks.

### Upgrade from v0.4.2 to v0.5.0

Version 0.5.0 includes a managed upgrade from the released v0.4.2 installation.
Update the Controller and console from the same v0.5.0 release. The installers
back up and remove retired application files while preserving:

- players, calibration, tuning, and dead-zone settings;
- camera and device configuration;
- pairing and the saved console address;
- game registrations and rapid-fire choices;
- ROMs, saves, controller assignments, and installed native cores.

Keep the printed backup location until you have completed the reboot and game
checks above. If the installer reports an unknown or locally modified retired
file, follow its message rather than deleting the installation manifest or
forcing the upgrade. The
[technical installation reference](CONFIGURATION_REFERENCE.md#versioned-multi-platform-installation)
describes staged upgrades and recovery.

Use this order for the release upgrade:

1. Close every running game. On LaunchBox, also close LaunchBox, Big Box, and
   RetroArch.
2. Install v0.5.0 on the Controller, then install the same release on the
   console. Run each command from the writable folder shown in its platform
   section; do not mix stable and release-candidate files.
3. Keep every backup location printed by the installers until acceptance is
   complete.
4. Reboot the Controller and console. Confirm pairing, players, calibration,
   game registrations, and Controller Router assignments were retained.
5. Test physical controls, VirtualGlove controls, the platform exit hotkey, and
   native Super Glove Ball when its core is installed.

### Read the installer report

| Result | What it means |
| --- | --- |
| `PASS` | That check succeeded. |
| `ACTION` | Installation succeeded, but you still need to complete the named step, such as pairing or testing a game. |
| `FAIL` | Resolve the reported problem before continuing, then run the installer again. |

A technical `PASS` cannot prove that your camera sees your hand or that a game
responded. Complete the physical game checks before considering installation
finished.

## If something does not work

### The download fails

Confirm internet access and retry the same command. A failed download or
checksum installs nothing. If the latest stable release does not contain the
required installer asset, wait for the completed release rather than using a
file from a different version.

### Dashboard or Setup does not open

Try the Controller's IP address instead of its `.local` name:

- Dashboard: `http://CONTROLLER-IP:8088/dashboard`
- secure Setup: `https://CONTROLLER-IP:8443/setup`

Confirm the Controller and browser are on the same local network. The Matrix
hourglass means VirtualGlove is still starting; a blinking X means Dashboard
has an error to report.

### The camera is unavailable

Open **Play** or **Glove Academy** and wait for the camera view. Reconnect the
camera, powered hub, and cable if it remains unavailable. The recovery helper
enrolls a supported camera after its first successful frame, even when no camera
was connected during installation. Do not change advanced camera settings until
the automatic configuration has been tested.

### Pairing fails or expires

Confirm the saved platform and address, run **Check console address**, and start
a new Controller confirmation. Obtain a new console code; expired PINs and
one-time codes cannot be reused. LaunchBox does not support SSH-password
pairing. Never copy pairing credentials between consoles manually.

### The game launches but hand controls do not work

Check these in order:

1. Dashboard shows **Start controller** as active.
2. The game filename is registered under **Setup -> Games**.
3. Dashboard shows the expected active game and profile.
4. The camera sees a calibrated hand.
5. The platform uses the VirtualGlove controller arrangement described in its
   install section.

If Controller Router is enabled, rest the hand at its saved neutral position
once after launch. Physical controls should work immediately; you must not need
to stop VirtualGlove to make a physical Start press work. If stopping
VirtualGlove is required, close the game and rerun the current console installer
to update Router. Do not replace the entire RetroArch configuration to repair
one binding.

### The wrong physical controller is Player 1

On RetroPie, Recalbox, or Batocera with Controller Router enabled, close every
RetroArch game and use Setup's **Controller Router** card. Assign the controller
to the intended player, save, and run the ten-second controller check. A red
Player 1 warning means no physical Player 1 controller can carry the platform
hotkey. On ordinary RetroPie without Router, or on LaunchBox, use the platform's
normal controller assignment while keeping VirtualGlove's managed entry intact.

### Super Glove Ball uses the wrong core

Confirm that the exact ROM filename is registered for Super Glove Ball. On
RetroPie, choose `lr-nestopia-powerglove` from the per-ROM launch menu. On
Recalbox, Batocera, or LaunchBox, restart the platform integration after adding
the ROM and confirm that no explicit per-game emulator choice overrides the
automatic selection. FCEUmm remains a safe fallback.

### Installation stops partway through

Correct the reported problem and rerun the same installer. Keep the backup path
printed by the installer. For service commands, logs, manual repairs, or package
details, use the [Troubleshooting Guide](TROUBLESHOOTING.md) and
[installation troubleshooting commands](CONFIGURATION_REFERENCE.md#installation-troubleshooting-commands).

## Matrix and web-page quick reference

These are the Matrix states most useful during installation:

| Display | Meaning |
| --- | --- |
| System heart or pulsing hourglass | The Controller is starting. |
| Animated glove | Gestures are off and the Controller is idle. |
| Scanning `L` | Play or Glove Academy practice is active; game output is paused. |
| `1`-`14`, `A`-`I`, `BS`, or `GB` | The corresponding game profile is selected. |
| Pulsing profile code | A calibrated hand is being tracked. |
| Blinking X | Open Dashboard to read the reported problem. |
| Blank | Check Controller power and Dashboard; blank does not confirm shutdown. |

See the [Matrix Guide](MATRIX_GUIDE.md) for every animation and display state.

| Page | Normal address |
| --- | --- |
| Dashboard | `http://UNO-Q-NAME.local:8088/dashboard` |
| Play | `http://UNO-Q-NAME.local:8088/play` |
| Glove Academy | `http://UNO-Q-NAME.local:8088/learn` |
| Setup and Games | `http://UNO-Q-NAME.local:8088/setup` |
| Secure pairing | `https://UNO-Q-NAME.local:8443/setup` |
| Help and printable manuals | `http://UNO-Q-NAME.local:8088/help` |

For gestures and game controls, use the [Gameplay Guide](GAMEPLAY_GUIDE.md).
Technical details are in [Architecture](ARCHITECTURE.md),
[VirtualGlove Input Modes](INPUT_MODES.md), and the
[Configuration Reference](CONFIGURATION_REFERENCE.md).
