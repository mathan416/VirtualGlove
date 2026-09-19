# VirtualGlove Input Modes

VirtualGlove can control an NES game in two different ways. **Joystick mode**
turns recognized gestures and hand movement into ordinary NES controller input.
**Native Power Glove mode** gives a compatible game the position-and-pose packet
it expects from the original glove.

Most games use joystick mode. Super Glove Ball can use either mode, although
native mode provides its distinctive continuous Robo-Glove movement.

This guide explains what the modes do, how physical controllers participate,
how to choose the right mode, and what to check when controls do not behave as
expected. The [Game and Gesture Guide](GAMEPLAY_GUIDE.md) remains the reference
for individual programs and gestures.

## Choose the right mode

| You want to… | Use | Emulator |
| --- | --- | --- |
| Play an ordinary registered NES game | Joystick mode | FCEUmm |
| Use Programs 1-14 or A-I | Joystick mode | FCEUmm |
| Use gestures and a physical controller together | Joystick mode | FCEUmm |
| Play Super Glove Ball with continuous hand position | Native Power Glove mode | Nestopia (VirtualGlove) |
| Play Super Glove Ball as a conventional NES game | Joystick mode | FCEUmm |
| Temporarily use only the physical controller | Gestures off or Program 14 | The game's selected emulator |

Changing modes does not require a second camera calibration. Both paths begin
with the same camera, selected player, saved centre, hand scale, reach, and
gesture recognition.

## How joystick mode works

Joystick mode presents familiar RetroPad controls to FCEUmm: D-pad, A, B,
Start, and Select. The active profile decides which recognized movement or
gesture produces each control. Returning the hand to its saved centre releases
movement, and tracking loss safely releases every VirtualGlove control.

The console receives authenticated, current controller state. It does not
replay a queue of old hand positions. Rapid-fire settings are applied at the
console and can be changed from the Dashboard while the game is running.

### Player 1 on each platform

| Platform | How joystick-mode Player 1 works |
| --- | --- |
| RetroPie — standard installation | VirtualGlove appears as a separate **VirtualGlove** gamepad. Existing physical controllers remain separate and continue to work. |
| RetroPie — routed cabinet | Optional **Controller Router** can combine configured I-PACs, joypads, and VirtualGlove into **VirtualGlove Merged Player 1–4**. The standard installation remains unchanged until Router is explicitly saved and applied. |
| Recalbox | **Controller Router** creates enabled merged Players 1–4. The released Player 1 selection migrates automatically, while the original controllers continue to operate EmulationStation. |
| Batocera | Uses the same **Controller Router** model as Recalbox and resolves current Linux and RetroArch indexes at every FCEUmm launch. |
| LaunchBox | The physical XInput controller remains Player 1. VirtualGlove joins it through RetroArch's loopback Network RetroPad. The real keyboard remains available. |

### Standard RetroPie and the VirtualGlove arcade cabinet

A fresh RetroPie installation does not need a merger. The standard installer
creates one `VirtualGlove` gamepad, installs its RetroArch mapping, and leaves
the console's existing joypads untouched. This is the arrangement that worked
on a clean RetroPie installation and remains the supported default.

The VirtualGlove development cabinet has a second, optional project component
because it has several ways to control the same players. Its
`arcade-gamepad-merger` combines the two I-PAC gamepad interfaces, supported
8BitDo controllers, and VirtualGlove into two canonical outputs:

- **Arcade Merged Player 1:** I-PAC Player 1 + 8BitDo Player 1 + VirtualGlove.
- **Arcade Merged Player 2:** I-PAC Player 2 + 8BitDo Player 2.

The merger rediscovers sources after connection changes instead of saving an
`eventN` path. A button stays pressed while any source holds it, and removing a
source releases only that source's controls. VirtualGlove contributes NES
Select but cannot produce the merged device's dedicated hotkey-enable button.

This cabinet component was authored as part of the VirtualGlove work and is now
preserved under `retropie/arcade-cabinet-merger/`. It was previously deployed
directly to `/usr/local/sbin/arcade-gamepad-merger`, which is why its source was
missing from the repository even though it belonged to the project.

The checked-in version intentionally retains the proven cabinet mappings as a
reference and one-command rollback source. New configurable installations use
Controller Router. The cabinet is migrated only after its proposed I-PAC,
8BitDo, and VirtualGlove assignments pass live validation. The cabinet helper
requires a fresh preflight receipt before `apply`; `rollback` restores the old
service state, Router file, FCEUmm override, and receiver route.

### Controller Router

Those platforms normally discover a physical controller, read its
EmulationStation mapping, and generate a RetroArch assignment at game launch.
Trying to add a second Player 1 after that process can change button meanings,
move a controller to another index, or let one press reach both RetroArch and a
platform hotkey handler.

VirtualGlove therefore creates up to four canonical gameplay devices named
**VirtualGlove Merged Player 1–4**:

1. Setup inventories only controllers already configured by EmulationStation.
   The user reviews suggested frontend-order assignments before anything is saved.
2. The versioned `controller-router.json` records stable identities, authoritative
   EmulationStation mappings, enabled players, and at most one VirtualGlove player.
   It never stores `/dev/input/eventN`, `/dev/input/jsN`, or a RetroArch index.
3. At boot, Router finds each saved source and creates only the enabled outputs.
4. At game launch, the current Linux event device and current RetroArch joypad
   index are resolved again. USB enumeration may change without changing the
   selected controller.
5. During FCEUmm gameplay only, Router takes exclusive ownership of assigned
   physical event device. This prevents the original device, the platform
   hotkey service, and the merged device from interpreting the same press.
6. Buttons remain held while any assigned source holds them. For each physical
   axis, the latest active source owns it until neutral; another still-active
   source then resumes. Any non-neutral physical source outranks VirtualGlove.
7. At game exit, every merged state is neutralized before exclusive ownership is
   released. EmulationStation then continues using the original controller.

The managed Player assignments live in FCEUmm's core-specific RetroArch
override. Nestopia (VirtualGlove) does not load that file, keeping native Super
Glove Ball outside Router and preserving its physical-controller path.

The physical controller's own hotkey is mapped to a dedicated merged button.
VirtualGlove Select can emit only NES Select; it cannot enable RetroArch
hotkeys. This is why Select no longer opens the RetroArch menu while still
working in a game.

If a physical controller disconnects during play, only its held inputs are
released. VirtualGlove can remain active, and the saved controller reconnects
when the same device returns. If several indistinguishable controllers are
present, the installer requires an explicit Player 1 choice rather than
guessing.

One physical source can belong to only one player, but several physical sources
may share a player. The one paired VirtualGlove can be unassigned or assigned to
exactly one player. Physical-only configurations are valid and need no pairing.
Only Player 1 carries a physical hotkey. Player 2–4 hotkeys are ordinary or
ignored controls, and VirtualGlove can never emit the hotkey-enable button.

### Local assignment screen

Run `sudo /opt/virtualglove/bin/virtualglove-controller-router setup` on
RetroPie. On Recalbox and Batocera, use `sh` with the persistent
`scripts/virtualglove-controller-router setup` launcher inside the VirtualGlove
installation because their persistent shares are mounted without direct program
execution. The dependency-free screen detects the
platform, shows stable controller identities and connection state, and lets the
operator assign each source or VirtualGlove to Players 1–4. **Test controls**
reports live buttons and directions without launching a game. Nothing changes
until **Save and verify** is confirmed, and the prior assignment can be restored
from the same screen.

The local screen does not create or replace a pairing credential. Pairing
authorizes the VirtualGlove Controller and its web Setup page to reach the
console; routing decides which FCEUmm player receives each already configured
input source.

FCEUmm recognizes known Four Score games by CRC. Four merged outputs do not make
an ordinary game four-player. For a compatible altered ROM that FCEUmm does not
recognize, the advanced registry setting `"four_score": "force"` selects its
User 5 four-player adaptor; leaving the field out keeps automatic detection.

### What the merger does not change

- It does not rewrite the controller's EmulationStation mapping.
- It changes only enabled NES/FCEUmm Player 1–4 assignments.
- It does not depend on the order in which USB devices appeared after boot.
- It does not make the merged device navigate the frontend.
- It does not let VirtualGlove gestures activate the physical hotkey.

## Test joystick mode

Use a registered FCEUmm game such as Super Mario Bros.:

1. Confirm that the physical controller works in EmulationStation.
2. Launch the game and wait for the title screen.
3. Use the physical controller to test directions, A, B, Start, and Select.
4. Start the VirtualGlove Controller and test the corresponding gestures.
5. Hold a physical direction while making a different VirtualGlove movement.
   The physical direction should remain authoritative until released.
6. On a routed console, press physical Select by itself. It must behave as
   Select and must not open the RetroArch menu.
7. Test the platform's physical hotkey combinations, including menu and exit.

After a reboot, repeat steps 2-4. A changed event number or joypad index should
not require reconfiguration.

## How native Power Glove mode works

Native mode is available for the exact registered Super Glove Ball game through
the separately named **Nestopia (VirtualGlove)** core. Stock Nestopia remains
untouched, and FCEUmm remains available as the conventional fallback.

The shared Controller-to-console receiver publishes one coherent, current
native-state sample. Nestopia (VirtualGlove) reads at most one sample per
emulated frame and converts it into the ten-byte Power Glove packet used by the
validated game. It adds no replay queue and no second smoothing layer.

In joystick mode, moving far enough right means “hold Right.” In native mode,
the calibrated position means “place the Robo-Glove at this X/Y coordinate.”
That difference is the reason native mode can track continuous movement inside
the playfield.

| What you do | Confirmed native Super Glove Ball behavior |
| --- | --- |
| Move horizontally or vertically | Position the Robo-Glove continuously in X/Y |
| Open the hand | Release or throw |
| Close the hand | Grab or catch |
| Point with the index finger | Fire Robo-Bullets |
| Make a fist and push forward | Power Punch |
| Use the Start gesture | Start the game |
| Press physical Player 1 Start | Start the game through the same confirmed native action |

Every action needed to complete the game has been confirmed in live play.
Wrist rotation and unobserved native button fields remain neutral because the
validated game has not demonstrated a required action for them. Guessing packet
values would risk unintended input.

### Safety and freshness

Missing calibration, the wrong profile, lost tracking, invalid state, or a
sample older than 250 milliseconds produces neutral native input. A brief
missed observation may retain only X/Y for up to 180 milliseconds while actions
release. Recovery accepts aligned forward movement immediately and guards one
strongly contradictory or unusually distant result.

The emulator core reported by the console is part of the authenticated game
session. Native output is enabled only for the combination of the
`super_glove_ball` profile and Nestopia (VirtualGlove). The same ROM in FCEUmm,
another core, or an unknown core receives joystick-mode output instead.

## Select native Super Glove Ball

The installer adds Nestopia (VirtualGlove) without replacing another emulator.
Exact-ROM selection is automatic where the platform supports it, but an
existing per-game choice is preserved.

1. Register the exact Super Glove Ball ROM in Setup.
2. Confirm the console installation check reports the optional native core as
   available.
3. Choose **Nestopia (VirtualGlove)** for that ROM if the platform has preserved
   a previous emulator choice.
4. Launch the game before starting the Controller so the emulated glove is
   attached during the game's detection sequence.
5. Start the Controller and use the Start gesture or physical Start.

To return to conventional controls, select FCEUmm for that ROM. This does not
change player calibration, gesture tuning, the physical controller mapping, or
the ROM.

## Native support by platform

| Platform | Native-core installation and selection |
| --- | --- |
| RetroPie | Builds the separate Linux core from pinned source and offers it as a per-ROM emulator. |
| Recalbox | Installs a verified architecture build in persistent storage and exposes it through reversible runtime overlays. |
| Batocera | Selects and verifies the packaged architecture build, then exposes it through reversible overlays and a per-ROM choice. |
| LaunchBox | Installs a separately named x86-64 DLL and uses the VirtualGlove RetroArch wrapper for the exact registered ROM. |

If the native artifact is missing, changed, incompatible, or not selected,
VirtualGlove safely uses FCEUmm joystick mode. Installers never replace stock
Nestopia.

## Confirmed compatibility boundary

Native behavior is validated against `Super Glove Ball (USA)` with SHA-256:

`ad60ef1b62cd1b3bc02a9320376067347a8ab2ebbe46e1616693d8379c9d9a7b`

The ROM is not included with VirtualGlove. The exact game reads ten bytes per
sample, requires the final validation byte, and consumes native X/Y, signed
depth, pose, and Start values confirmed by controlled traces and live play.
These results are not a claim that every ROM revision or Power Glove-compatible
game uses the same packet fields.

Headless same-state tests found the first visible directional response on frame
3 for both this native path and the same ROM in FCEUmm. That isolates emulator
response; it does not include camera exposure, recognition, network delivery,
or display latency. The investigation and rejected alternatives are preserved
in the [Engineering Journey](ENGINEERING_JOURNEY.md).

## When controls do not work

Check the visible symptom first:

- **Physical controller works in the frontend but not in a Recalbox/Batocera
  game:** rerun the console installer check. Confirm that the saved Player 1 is
  connected and the merged gamepad is assigned.
- **Buttons are rearranged:** do not manually copy SDL button numbers into Linux
  event mappings. Re-run the current installer so it refreshes the saved
  EmulationStation mapping, then restart the game.
- **Select opens the RetroArch menu:** the physical controller is reaching both
  the platform hotkey service and the merged path. Exit the game and restart
  the VirtualGlove console service or rerun the current installer.
- **VirtualGlove works but the physical controller disappeared:** reconnect the
  selected controller. If it was replaced with a different model, rerun the
  installer and select the new Player 1 device.
- **Super Glove Ball moves like a D-pad:** the game is running in FCEUmm. Choose
  Nestopia (VirtualGlove) for continuous native movement.
- **Super Glove Ball does not detect native input:** confirm the registered ROM,
  selected core, calibration, and active Controller status. Then exit and
  relaunch so the native peripheral is attached before detection.
- **Controls remain held after interruption:** stop the Controller and exit the
  game. Timeout, disconnect, game-exit, and service-shutdown paths all publish a
  neutral state; use the [Troubleshooting Guide](TROUBLESHOOTING.md) if they do
  not.

For installed paths, device records, service checks, and command-line options,
see the [Configuration Reference](CONFIGURATION_REFERENCE.md). For packet and
ROM-level evidence, see the [Power Glove Game Input Audit](power-glove-rom-input-audit.md).
