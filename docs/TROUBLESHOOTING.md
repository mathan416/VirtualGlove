# Troubleshooting by Symptom

Start at the first stage that fails: camera, recognition, Controller delivery,
console reception, emulator selection, then the displayed game. Keep a normal
gamepad available. Change one setting at a time so you know what fixed the issue.

<img src="images/gestures/v2/pixel-pal-safety.png" alt="Pixel Pal gives a friendly stop-and-check signal" width="150">

The **VirtualGlove Controller (Arduino UNO Q)** hosts Setup, Glove Academy,
and Help. Use **Help → This console** for addresses specific to your installation.
The examples below use placeholders, not addresses that every build shares.

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
3. Try `http://CONTROLLER-IP:8088/setup`. Secure pairing uses `https://CONTROLLER-IP:8443/setup`.
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
| Grey | The host report is missing, stale, incomplete, or has no recognized interface | Check that the Controller host sampler was installed/upgraded; do not assume the cable is disconnected |

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
instead of repeatedly presenting a broken preview. This behavior belongs to the
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

## The camera works but the hand is not recognized

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

1. Close local Play and Glove Academy; they pause cabinet input. Finish tuning, then explicitly start controller delivery if required.
2. Check the selected player and any request to set a fresh centre. Selecting a player loads their saved centre automatically. Use **Center hand** if no centre is saved or the camera or playing position has changed.
3. Select **Start controller**. Armed means delivery is permitted when a valid game session or intentional manual profile is active; it does not mean packets are always being sent.
4. Check Setup's console-service and authenticated-response markers. A reachable service with unconfirmed authentication suggests pairing needs attention. Neither marker proves emulator input consumption.
5. Confirm that the game has actually started in RetroArch. The exact ROM filename must be registered; `.nes`, `.zip`, and `.7z` are separate entries.
6. Check the emulator and controller selection. For native Super Glove Ball, choose Nestopia (VirtualGlove); for its joystick fallback choose FCEUmm.

If Controller Router is enabled, return the hand to neutral once after the game
appears. Router deliberately rejects directions and button gestures until that
fresh neutral observation, while physical controls remain available
immediately. If no physical controller responds until VirtualGlove is stopped,
the console has an older Router build; close the game and rerun the current
console installer.

If the ROM was added after VirtualGlove was installed, refresh the frontend's
game list before testing it. Recalbox and Batocera also need a VirtualGlove
service restart or reboot after a newly registered Super Glove Ball ROM so the
missing exact-ROM native choice can be created. In LaunchBox, rerun the current
installer if an older installation still points **VirtualGlove RetroArch** at a
batch file or leaves standard RetroArch assigned to an NES game. The current
installer uses the Python bridge directly and migrates standard RetroArch NES
assignments while preserving genuinely different emulator overrides.
The bridge also ensures the managed receiver on every launch. If Dashboard
shows **Controller connection stopped** while a LaunchBox game is active, close
the game and LaunchBox, rerun the current installer, and relaunch the game. The
upgrade stops duplicate receivers left by an older Python environment without
changing ROMs, saves, pairing, or the game registry.

If native hand movement reaches Super Glove Ball on LaunchBox but the V-sign
Start gesture or thumbs-up Select gesture does not, close RetroArch and rerun
the current installer. Current builds keep native gestures on the guarded Power
Glove channel instead of also sending ordinary RetroPad input. Dashboard recognition plus a working physical joypad does not
by itself prove that an older Windows receiver has this correction.

On generic RetroPie, confirm the separate `VirtualGlove` input device and its
Player 1 mapping. If optional Controller Router is enabled—or on Recalbox and
Batocera—open its Setup card or run `virtualglove-controller-router check`.
Confirm each saved source is connected, every enabled **VirtualGlove Merged
Player 1–4** output exists, and the current FCEUmm player indexes are assigned.
Merged devices are intentionally neutral in EmulationStation. On LaunchBox, the installer must
report `network-retropad`, a random high loopback port, and a validated isolation
rule. A reported key conflict affects only the real-keyboard backup; VirtualGlove
and physical XInput remain available. If gestures are recognized but FCEUmm does
not move, rerun the current installer to restore the managed ordinary-game
configuration and receiver route rather than changing global RetroArch settings.
If LaunchBox reports that Nestopia (VirtualGlove) is missing or changed, rerun
the matching VirtualGlove Windows installer. The affected game continues in
FCEUmm joystick mode. On Batocera, an **ACTION** result for the packaged native
core means the architecture could not be resolved or the on-console load test
failed; leave FCEUmm selected and do not copy a core from another target.
Verify the matching platform service from the [Installation Guide](INSTALL_README.md#3-install-the-console)
before editing RetroArch settings.

If a fresh Recalbox/Batocera update reports several possible initial Player 1 controllers,
run the installer with `--list-player1-devices`, identify the intended pad, and
repeat it with `--player1-device DEVICE-ID`. Two identical, non-serialized pads
are not guessed. If the selected pad disconnects during play, only its held
state releases; VirtualGlove remains available. Reconnect that saved pad, or
explicitly select its replacement. Seeing no response from the merged device in
EmulationStation is expected—it deliberately becomes active only in RetroArch.

A filename such as `Gun.Smoke (USA).7z` must keep its punctuation in the registry
even though the displayed game name is **Gun Smoke**. See
[Register games](CONFIGURATION_REFERENCE.md#register-games-and-select-profiles)
and the [Gameplay Guide](GAMEPLAY_GUIDE.md).

## Pairing asks for more than one code

Both pairing methods need the six-digit approval PIN displayed on the Controller
matrix and the certificate-ID comparison. **Code pairing** additionally uses the
one-time code generated on the selected console. **Password pairing** additionally
uses that console's SSH username and password. The two codes are not interchangeable.

If confirmation expires, select **Start a new confirmation**. The saved console
and method stay fixed during the two-minute window; change them after it ends.
A failed submitted request also requires fresh confirmation. Save console edits
with **Save settings** before pairing.
The separate console one-time code remains valid for five minutes. Setup shows
the correct command after RetroPie, Recalbox, Batocera, or LaunchBox is selected and saved.
LaunchBox uses one-time-code pairing only. Run the displayed PowerShell command
as the same Windows user who runs LaunchBox. If Windows asks about network
access, allow the Python runtime on Private networks only. VirtualGlove's
authenticated receiver runs in that signed-in desktop session, but ordinary
game input reaches RetroArch through the managed loopback RetroPad and is not
conditioned on window focus. A focus change must not release an active held
control; tracking loss, controller timeout, game exit, or receiver shutdown does.
If more than one console is online, run it on the exact console named in Setup;
a code displayed by a different console cannot open the intended listener. A
platform-mismatch error means the saved selection does not match the operating
system detected by that console; correct and save the selection before retrying.
When a submitted pairing attempt finishes, the matrix releases the approval PIN and resumes its normal display. When idle, the glove animation follows your On, Dim, or Off attract setting; active game and status displays still take priority. A completed attempt should not leave the old PIN scrolling for the rest of its two-minute window.

Use the [pairing walkthrough](INSTALL_README.md#4-pair-the-devices); never paste
pairing tokens, passwords, or live approval PINs into a public support report.

If a saved DHCP address changes or `.local` is briefly unavailable, leave the
pairing key in place. Both controller input and game-profile delivery can discover
the paired peer on the same ordinary LAN and resume by authenticated unicast. Guest
isolation, VLANs, or blocked local broadcasts can prevent discovery; enter a current
address or repair local name resolution in that case rather than pairing repeatedly.

## Movement drifts or feels reversed

Check the selected game profile and centre before changing sensitivity. Hold a
relaxed hand at the intended playing position and choose **Center hand**.
Support your forearm where practical. Re-centre after moving the camera.

A profile such as Program D intentionally reverses controls. Native Super Glove
Ball and joystick-style mappings behave differently, so verify the selected core.
Programs 4, 9, 10, 13, and 14 also use deliberately specialized controls rather
than the ordinary position-based D-pad. Before retuning recognition, compare the
selected profile with the [complete Programs 1-14 gesture cards](GAMEPLAY_GUIDE.md#program-cards-1-14).
If ordinary movement is correct but a gesture is unreliable, use **Glove Academy
→ Tune gestures** and describe that symptom to Pixel Pal.

For FCEUmm digital directions, Setup's **Joystick dead zone** adjusts how far
the selected player moves beyond the square center box. Inside or on its boundary,
all positional directions release; beyond a side is a cardinal direction and beyond
a corner is a diagonal. Start with **Use standard size**, then save one small change
at a time while watching the live direction indicators. The box is anchored to
the hand center saved by **Center hand**, and its effective width and height are
at least 1.5 times the saved hand size. Near an edge it moves inward intact.
Live hand size and resting jitter do not make it change. Slider changes preview immediately; Save applies them to
gameplay. This setting does not
change native Super Glove Ball X/Y travel or cure processing latency. Use reach
controls under **Glove Academy → Tune gestures → Movement reach** for native
screen coverage and the latency procedure below for delay. Smaller reach values
need less physical hand travel. **Latest coordinate** is the tested default;
it is the only live native movement behavior and clamps at the saved reach
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
accidentally** in Tune gestures if recognition needs personalization.

Menu Guard suppresses D-pad and button output; native continuous positioning
still follows the hand. Select **Stop controller** for a dependable pause while
repositioning. Do not use extra smoothing to hide a recognition problem.

## Controls feel delayed

Close optional camera previews during gameplay. Keep lighting and camera setup
stable, then compare deliberate movements and supported stationary holds. Avoid
changing several camera, core, and display settings at once.

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
object can simply mean defaults are in use. Version-3 backups carry the center-box
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
