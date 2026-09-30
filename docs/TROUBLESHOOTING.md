# Troubleshooting by Symptom

Start at the first stage that fails: camera, recognition, Controller delivery,
console reception, emulator selection, then the displayed game. Keep a normal
gamepad available. Change one setting at a time so you know what fixed the issue.

<img src="images/gestures/v2/pixel-pal-safety.png" alt="Pixel Pal gives a friendly stop-and-check signal" width="150">

The **VirtualGlove Controller (Arduino UNO Q)** hosts Setup, Glove Academy,
and Help. Use **Help → This console** for addresses specific to your installation.
The examples below use placeholders, not addresses that every build shares.

## A console upgrade was interrupted

1. Keep the console connected and close any running game.
2. Rerun the same VirtualGlove installation command. A pending upgrade is recovered before software replacement begins again.
3. Watch for **RECOVERED**. This confirms restoration of the previous managed software, configuration, and service state.
4. If recovery fails, retain the printed backup directory and its pending journal. A checksum error means the installer has refused an unverified recovery copy; a service error leaves the journal available for another recovery attempt.

Normal installation or validation errors trigger recovery immediately. Pairing credentials, registries, permissions, and ownership are preserved. Operating-system package changes are outside this recovery.

## Buster package source moved

An older RetroPie image may stop during installation with a message that
`raspbian.raspberrypi.org/raspbian buster` has no Release file. Buster has moved
to Raspbian's legacy archive. This is an operating-system package-source issue,
not a VirtualGlove package failure. The installer detects it before changing
the VirtualGlove payload.

A newly imaged, supported RetroPie system is the best long-term fix. To keep an
existing Buster cabinet running, back up its source list and replace only the
retired Raspbian host:

```sh
sudo cp /etc/apt/sources.list /etc/apt/sources.list.before-virtualglove
sudo sed -i \
  's|http://raspbian.raspberrypi.org|https://legacy.raspbian.org|g' \
  /etc/apt/sources.list
sudo apt-get update
```

If the installer's message names a file under `/etc/apt/sources.list.d/`, back
up and make the same host-only replacement in that file. **Do not replace
`archive.raspberrypi.org/debian`**; it is a different Raspberry Pi repository.
After `apt-get update` succeeds, rerun the same RetroPie installer. Existing
pairing and settings remain intact.

## The website will not open

1. Check power and give the Controller time to finish starting.
2. Put your browser device on the same reachable LAN. Check the router's client list for the Controller's current IP address.
3. Try `http://CONTROLLER-IP:8100/setup`. Shared pairing uses `https://CONTROLLER-IP:8444/setup`.
4. If the IP works but `.local` does not, investigate hostname resolution and guest-network/client isolation. With Wi-Fi and USB Ethernet connected, the Controller can have more than one address.

Use the plain `/setup` address; no `?ui=2` suffix is needed. Old query-string bookmarks still open Setup.

### The first installer says the Controller name is already in use

Another device answered for the requested `.local` name. Rerun the installer
and choose a distinct short name, such as `virtualglove-den`. Do not disconnect
the other device merely to bypass the check: duplicate `.local` names can change
automatically and break browser bookmarks or console delivery. Updates do not
ask this question and never rename an installed Controller.

### The secure page shows a privacy warning

On the first visit, compare the website certificate with the ID on the physical
Controller matrix. When they match, use **Trust this Controller** on secure Setup
to download and install this Controller's public authority certificate. Trust
must be enabled once on each phone or computer. The private authority key is
never downloaded.

If a previously trusted Controller starts warning after an ordinary upgrade,
confirm that the browser is using the same hostname and inspect the certificate
before proceeding. Do not casually reset trust. If the authority files are
actually damaged, stop VirtualGlove, move `data/tls` to a specially named backup,
and start VirtualGlove again. This deliberately creates a new Controller
identity: compare its new Matrix ID and install its replacement authority on
each browser device.

Do not change pairing keys to fix an unreachable website. If SSH works, use the
[configuration troubleshooting reference](CONFIGURATION_REFERENCE.md#setup-page-does-not-open)
for application checks. The documented hardware may restart after Shutdown;
a disappearing page alone does not prove that power has been removed.

## Networking is red or grey

The fourth Setup marker and fourth Off-mode pixel represent a physical **Wi-Fi
or Ethernet link**, including supported Ethernet adapters in USB docks.

| Marker | Meaning | Next check |
| --- | --- | --- |
| Green | At least one detected physical Wi-Fi/Ethernet link is up | Check console-service and authenticated-response markers next |
| Red | Detected relevant links report disconnected | Check wireless association, Ethernet cable, dock power, and upstream data connection |
| Grey | The host report is missing, stale, incomplete, or has no recognised interface | Check that the Controller host sampler was installed/upgraded; do not assume the cable is disconnected |

Docker bridges and loopback do not make this marker green. A green link does
not prove an IP address, Internet access, console reachability, or game delivery.
Older Wi-Fi-only telemetry can confirm a connected wireless link but cannot
rule out Ethernet when Wi-Fi is down. Use the current Controller installer or
upgrade helper to update the host sampler.

## The camera view is missing

**Gestures off** normally closes the camera. Open **Play** or **Glove Academy**
and wait for **Starting camera and gesture tracking** to finish. First startup
can take longer than switching between active profiles.

When no camera is connected, Dashboard deliberately shows **Camera unavailable**
instead of repeatedly presenting a broken preview. This behaviour belongs to the
Controller and is the same for RetroPie, Recalbox, Batocera, and LaunchBox; it
is not a Recalbox-specific failure.

If no camera appears, check the powered USB hub, cable, and camera connection.
On the Controller host, `lsusb` should show the camera. If it is absent there,
the problem is below hand recognition. The documented helper attempts one
controlled recovery for the enrolled camera. A hub that proves per-port power
support cycles only the saved camera port; a guarded whole-hub fallback is used
only when the hub carries no networking. The Controller does not report success
until it reads a real frame.
Repeated setting changes will not repair a disconnected USB device. See
[Camera selection](CONFIGURATION_REFERENCE.md#camera-selection).

## The camera works but the hand is not recognised

Keep one whole hand in frame with its palm facing the camera. Light the hand
from the camera side and avoid a bright window behind it. Try a bare hand
before changing glove settings; the glove-colour option is only a diagnostic
label. Use the first Glove Academy lesson to verify basic detection.

If detection repeatedly disappears, fix visibility before tuning gesture
thresholds. Tracking losses and ordinary stationary jitter are different
problems and should be reported separately.

Current releases install MediaPipe Hands 0.10.35 as the single Controller
runtime. There is no user-selectable old-runtime fallback. If the worker reports
that its wheel is missing, rerun the current Controller installer rather than
adding a runtime setting to `device.json`.

## The hand is detected but the game does not move

1. Close **Play** and **Glove Academy** before playing on your console.
2. Choose your player. Use **Centre hand** if you moved the camera or changed your playing position.
3. Choose **Start controller** on Dashboard.
4. Open **Setup** and check the console connection. If it asks you to pair again, complete pairing before continuing.
5. Check that the game's filename is in your game registry. A zipped game and an unzipped game need their own entries.
6. For Super Glove Ball's hand controls, select **Nestopia (VirtualGlove)** on your console. For joystick controls, select **FCEUmm**.
7. After the game appears, rest your hand in the centre once, then try moving it.

If you just added the game, refresh your console's game list. On Recalbox or Batocera, restart the console after registering Super Glove Ball so its special emulator choice appears.

If the connection stops or a required emulator is missing, close the game and rerun the console installation command. It repairs the installed software while keeping your pairing, game registry, ROMs, and saves. The [Installation Guide](INSTALL_README.md) has the command for your console.

For platform-specific installation checks, see [Console input delivery](CONFIGURATION_REFERENCE.md#diagnose-console-input-delivery) in the technical reference.

### A gamepad does not control the game

Try another connected gamepad. The one in your hands may be assigned to
Player 2 while another pad is Player 1. In Setup > Controller Router,
check which pad belongs to each player. Close the game before changing
an assignment, then relaunch it to use the corrected routing.

### A wireless controller falls asleep or wakes during a game

Wake or reconnect the pad. Router keeps its player controllers connected and returns the pad to its saved player.

If the Router service itself restarted, exit the game, wait until it is ready, then relaunch. Player changes saved in Setup also apply on the next launch.

For a pad test, open Router **Setup > Players**, choose **Test inputs**, and press a button during the five-second check. The [Controller Router Guide](CONTROLLER_ROUTER.md) walks through changing players and systems.

### Controller Router reports an unavailable controller

Select **Check controllers**, then press a direction or button on every connected
pad during the ten-second test. Each result includes the controller name, its
stable six-character identity suffix, and its assigned player. For example,
`Wireless Controller · cd8a4a · Player 1` identifies the saved device without
depending on a changing Linux event number.

If a controller is listed as **Unavailable**:

1. Reconnect that exact controller and wait for EmulationStation to recognise it.
2. Confirm it still appears and works in EmulationStation.
3. Run **Check controllers** again and press one of its controls.
4. If the old controller was replaced, close every RetroArch game, assign the
   replacement in Controller Router, and save. Router never silently substitutes
   a different device.

A connected controller can report **Mapping refreshed** after a valid remap in
EmulationStation. Its player assignment is retained and the refreshed mapping
is used at the next game launch. If one controller responds while another is
missing, Setup reports both facts rather than treating the whole test as a pass.

If no physical controller is assigned to Player 1, Setup shows a red warning.
Gameplay may still work, but the platform's RetroArch menu and exit hotkeys may
be unavailable. Assign at least one physical controller to Player 1 unless a
keyboard is deliberately kept available.

Controller Router manages Libretro gameplay, not standalone emulator programs.
Original controllers continue to navigate EmulationStation. Do not use the lack
of merged-device movement in the frontend as evidence of a failure.

A filename such as `Gun.Smoke (USA).7z` must keep its punctuation in the registry
even though the displayed game name is **Gun Smoke**. See
[Register games](CONFIGURATION_REFERENCE.md#register-games-and-select-profiles)
and the [Gameplay Guide](GAMEPLAY_GUIDE.md).

## Pairing asks for more than one code

The **CR1 connection code** comes from the console installer and lasts five minutes. The **six-digit confirmation code** appears on the controller’s Matrix display after you choose Continue and lasts two minutes. Enter them in that order on Router’s **Pair console** page. No SSH password is needed.

If a code expires, is already used, or reaches the attempt limit, obtain a new console code and start again. If the Matrix is unavailable, wait for Controller Router to become ready; pairing cannot skip physical confirmation.

## Movement drifts or feels reversed

Check the selected game profile and centre before changing sensitivity. Hold a
relaxed hand at the intended playing position and choose **Centre hand**.
Support your forearm where practical. Re-centre after moving the camera.

A profile such as Program D intentionally reverses controls. Native Super Glove
Ball and joystick-style mappings behave differently, so verify the selected core.
Programs 4, 9, 10, 13, and 14 also use deliberately specialized controls rather
than the ordinary position-based D-pad. Before retuning recognition, compare the
selected profile with the [complete Programs 1-14 gesture cards](GAMEPLAY_GUIDE.md#program-cards-1-14).
If ordinary movement is correct but a gesture is unreliable, use **Glove Academy
→ Tune gestures** and describe that symptom to Pixel Pal.

For FCEUmm digital directions, Setup's **Joystick dead zone** adjusts how far
the selected player moves beyond the square centre box. Inside or on its boundary,
all positional directions release; beyond a side is a cardinal direction and beyond
a corner is a diagonal. Start with **Use standard size**, then save one small change
at a time while watching the live direction indicators. The box is anchored to
the hand centre saved by **Centre hand**, and its effective width and height are
at least 1.5 times the saved hand size. Near an edge it moves inward intact.
Live hand size and resting jitter do not make it change. Slider changes preview immediately; Save applies them to
gameplay. This setting does not
change native Super Glove Ball X/Y travel or cure processing latency. Use reach
controls under **Glove Academy → Tune gestures → Movement reach** for native
screen coverage and the latency procedure below for delay. Smaller reach values
need less physical hand travel. **Latest coordinate** is the tested default;
it is the only live native movement behaviour and clamps at the saved reach
edges. Historical bounded-curve replay is an engineering tool, not a Dashboard
setting. If the Robo-Glove still jumps after
the hand leaves and re-enters the picture, confirm that the Controller and
RetroPie are on the same current release before changing reach or smoothing.
Version 0.4.2 retains the guard for one contradictory or unusually distant non-forward
reacquisition for one fresh result while allowing strongly aligned forward
movement immediately.

## Start triggers accidentally, or a gesture stays active

Practise the V sign and its release in Glove Academy. Keep your fingers clearly
away from a menu pose while performing another action. Use **A gesture happens
accidentally** in Tune gestures if recognition needs personalisation.

Menu Guard suppresses D-pad and button output; native continuous positioning
still follows the hand. Select **Stop controller** for a dependable pause while
repositioning. Do not use extra smoothing to hide a recognition problem.

## Controls feel delayed

Close optional camera previews during gameplay. Keep lighting and camera setup
stable, then compare deliberate movements and supported stationary holds. Avoid
changing several camera, core, and display settings at once.

If movement pauses and then catches up in a burst, check the connection before
changing gesture or camera settings. This can happen on any supported platform
when the Controller or console uses Wi-Fi: delayed packet delivery can look like
slow or jerky recognition even when the hand is tracked correctly. Compare the
same movement with a wired connection, if available. If the physical joypad is
smooth but VirtualGlove catches up in bursts, investigate the Controller-to-console
network path; if both lag, check the emulator and display path too. This is a
diagnostic possibility on RetroPie, Recalbox, and LaunchBox, not a confirmed
platform-specific fault or a reason to change their network settings by default.

Batocera has a confirmed Wi-Fi power-saving case. VirtualGlove turns off power
saving on connected Wi-Fi interfaces when its service starts and again before
a game, including the next launch after a wireless reconnection. Wired and
disconnected Wi-Fi interfaces are unaffected. If movement still pauses and
jumps, run `iw dev wlan0 get power_save` on the Batocera console (substitute
the connected wireless interface if it is not `wlan0`); **Power save: off** is
expected while VirtualGlove is running. Check the Controller's link as well:
the Batocera setting cannot change power saving on the Controller or router.

Software status can locate processing delays but cannot measure the complete
hand-to-screen delay. Follow the layered method in the
[Engineering Journey](ENGINEERING_JOURNEY.md#validation-story-proving-that-movement-was-real)
before drawing conclusions from screenshots or timestamps on different
computers. Use the [Engineering Toolkit](ENGINEERING_TOOLKIT.md) only when the
ordinary camera and connection checks do not identify the cause.

## My player or backup looks wrong

Check **Active player** first: player selection applies across browsers. Progress
and settings live on the Controller, not in browser storage. Each downloaded
backup contains only the selected player's hand setup and excludes Academy
progress. Your browser usually puts it in Downloads with a player-based name,
such as `alex-virtualglove-hand-setup.json`.

Restore updates the selected player after review. An empty personal-threshold
object can simply mean defaults are in use. Version-3 backups carry the centre-box
size and effective gesture sensitivity; version-2 backups are migrated on import.
See [backup locations and restore choices](CONFIGURATION_REFERENCE.md#where-player-settings-and-backup-files-live).

## What to include when asking for help

Start with **Setup → Download system report**. It records the relevant versions,
camera/runtime choices, active profile/input mode, and connection-check results but
omits video, secrets, personal hand data, ROM names, and network addresses.

Record the exact software commit and matrix firmware from the page footer,
Controller board variant, camera/dock models, connection type, selected player
and profile, core, game filename, and steps that reproduce the symptom. Say
whether it occurs in Academy, local Rock Paper Scissors, or only in a cabinet
game. Include the four status results and any tracking losses.

Share a short relevant error excerpt or aggregate diagnostic report. Exclude
credentials and private video. Raw latency recordings should remain temporary
and local unless you explicitly choose to share them. See
[Contributing](CONTRIBUTING.md) for the project's testing and reporting workflow.

## Wrong player despite correct Router assignments

1. Exit the game and open **Setup** from the Controller Router page.
2. Under **Players**, check the named source assignments. Under **Systems**, confirm that the system uses **Controller Router**.
3. Relaunch the game. Sleeping or reconnecting physical controllers should return to their saved players without removing merged devices.
4. If only one core or game still selects the wrong player, inspect its RetroArch controller override. Core and game overrides load after the session settings and can replace them. Remove only a conflicting controller override you deliberately want Router to manage; retain unrelated game settings.

The current installer removes recognised obsolete Router indexes from its old FCEUmm and Nestopia blocks after a backup. It does not rewrite saved `retroarch.cfg` files during play. If Router itself restarts, end the game and relaunch once it is ready.
