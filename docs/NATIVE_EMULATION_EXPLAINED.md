# How native Power Glove emulation works

VirtualGlove offers two ways to turn the same recognized hand into game
input. Most supported games use ordinary NES-style directions and buttons.
Super Glove Ball can instead consume a native Power Glove packet through
**Nestopia (PowerGlove)**, the separate `lr-nestopia-powerglove` core.

The distinction is what the game receives. It does not require a second camera
system or a different hand calibration.

![Shared camera and MediaPipe front end branching on the console into conventional FCEUmm input or native Nestopia Power Glove input](images/architecture/end-to-end.png)

## Follow one hand movement

1. The **VirtualGlove Controller (Arduino UNO Q)** captures the newest camera frame. Older waiting frames are replaced rather than queued.
2. MediaPipe Hands finds hand landmarks. Shared calibration and gesture processing turn them into position, depth, finger, and pose states.
3. The Controller sends authenticated state to the paired console. Its receiver validates it and publishes the newest usable state.
4. The chosen emulator core presents that state as the kind of controller input the game understands.
5. The game updates its world, and the display shows the result.

Each stage takes time. Smooth movement does not imply zero latency, and a
successful send is not proof that a displayed frame has caught up.

The Dashboard is an observer of this path. Its preview and optional statistics
can be turned off without changing the coordinates or controller packets sent
to the paired console.

### Camera reader and buffer choices

OpenCV and Direct V4L2 change only how a camera frame enters the shared
MediaPipe path. OpenCV is the compatible, gameplay-validated default. Direct
V4L2 is a Linux engineering comparison that can expose the driver's frame time
and manual controls when the camera supplies the required MJPEG format. It may
fall back to OpenCV and is not inherently lower latency.

One camera buffer minimizes how much captured work can wait. Two buffers can
improve continuity on some camera and hub combinations. In either case,
VirtualGlove owns one latest-frame slot: a newer capture replaces an older
frame that inference has not started. The choice affects joystick and native
games equally because it occurs before the emulator paths split. Use Setup's
camera test to compare supported choices with the actual camera rather than
assuming that the more technical reader or larger buffer count is faster.

## Joystick-style input: directions and buttons

With FCEUmm, the console exposes VirtualGlove as Player 1 input. Generic RetroPie
uses a separate **VirtualGlove** virtual gamepad. Recalbox and Batocera expose
**VirtualGlove Merged Player 1**, combining a selected physical controller and
gestures in one NES gamepad while leaving the original pad in charge of the
frontend. LaunchBox retains physical XInput plus a loopback Network RetroPad
for FCEUmm games, with real keyboard bindings as a manual fallback. Native Super Glove Ball bypasses that RetroPad path
and consumes only the guarded native record, while its core additionally
carries physical Start and Select into the two confirmed native packet codes. A profile maps
recognized gestures to D-pad directions, A, B, Start, and Select.
Moving sufficiently left of your saved centre can press Left; returning toward
centre releases it. Activation and release thresholds help avoid repeated
presses near the boundary.

This is useful for games expecting a conventional controller. Original Programs
1–14 and cartridge Programs A–I change which gestures produce those controls;
registered titles can also apply the documented rapid-fire exceptions. They do
not teach the game to understand continuous hand coordinates. FCEUmm remains an
explicit, complete joystick-style fallback for Super Glove Ball.

The numeric set also includes deliberate hybrid and no-gesture modes. Program 2
keeps Program 1 joystick output while adding live centering feedback. Program 13
keeps the camera active for gesture A/B but emits no camera D-pad, allowing the
merged physical Player 1 controller to provide movement. Program 14 closes the
camera and neutralizes every VirtualGlove control while retaining the visible
profile and authenticated game session. These are still joystick-session
profiles; none activates the native packet path.

Three numeric profiles deliberately change how the camera participates:
Program 2 adds live centering feedback without changing the saved calibration;
Program 13 emits gesture-based A/B and leaves D-pad movement to the merged
physical Player 1 controller; Program 14 closes the camera and emits no
VirtualGlove controls while keeping the game session visible. The detailed
gesture and game tables are in the [Gameplay Guide](GAMEPLAY_GUIDE.md#program-cards-1-14).

That same-player hybrid is automatic on Recalbox/Batocera through their merged
gamepad and on LaunchBox through physical XInput plus the local RetroPad. Generic
RetroPie intentionally installs a separate VirtualGlove gamepad; use its normal
controller assignment or an explicitly configured local merger.

<!-- PAGEBREAK -->

## Native input: a position inside a packet

In the native path, the receiver also publishes a small latest-state record at
`/run/virtualglove/native-state`. The custom core takes a coherent snapshot at the
start of its input callback and converts it into the emulated Power Glove's
packet. It does not accumulate a queue of past movements.

For the validated Super Glove Ball ROM, the game reads a ten-byte sample.
Its fields include detection, X/Y position, depth, hand pose, a button field,
and a validation terminator. Moving your hand changes a coordinate instead of
only switching a direction on or off. That is why this path can offer more
natural Robo-Glove positioning.

MediaPipe Hands supplies every live coordinate. Geometry is validated and the
point is clamped to the saved reach before it is published. **Latest
coordinate** uses each newest point directly during continuous tracking and is
the only live native movement behavior. Historical bounded-curve tooling remains
available for engineering replay, but it is not a Controller setting. Latest
uses the selected frame's capture time, saved center, and per-player reach. A
short missed observation may hold only X/Y for up to 180 ms
while actions release. On recovery, Latest accepts aligned forward movement at
once but holds one contradictory or unusually distant non-forward measurement
for the next fresh result. This one-result guard rejects reacquisition jumps
without predicting a position or smoothing ordinary motion.

The running core, not merely the ROM profile, decides whether this packet path
is active. The console's game-session integration detects the libretro core and
includes it in the authenticated profile heartbeat. Only `super_glove_ball`
with the separately named Nestopia (VirtualGlove) core selects native input.
FCEUmm, another core, or an unknown core selects ordinary joystick input.

| What you do | Native Super Glove Ball behavior confirmed in live play |
| --- | --- |
| Move the hand horizontally or vertically | Continuous Robo-Glove X/Y positioning |
| Open the hand | Release or throw |
| Close the hand | Grab or catch |
| Point with the index finger | Fire Robo-Bullets |
| Make a fist and push forward | Power Punch |
| Use the Start gesture | Start the game |

These findings include a successfully completed game. They apply to the exact
ROM and implementation documented in the [native compatibility record](super-glove-ball-native.md).
They are not a claim about every Power Glove-compatible game or ROM revision.

## Additional native fields

Every implemented action required to complete Super Glove Ball has been
confirmed in live play. Wrist rotation is still recognized by VirtualGlove, but
it and the remaining unused native packet fields stay neutral because no
required in-game action has been identified for them. Bytes 7–8 remain at
Nestopia's fixed `$00` initialization. Successful play at zero does not prove
that every ROM ignores those fields.

A field should only be enabled when a repeatable game behavior and a controlled
test justify it. Guessing from a packet diagram can introduce unintended actions.
The [packet table](super-glove-ball-native.md#confirmed-exact-rom-packet) separates
confirmed meanings from the parts still under investigation.

Menu Guard suppresses ordinary D-pad and button output but does not freeze native
continuous positioning. Select **Stop controller** when you want to reposition
without sending controls.

## Why the custom core is separate

The modified core preserves stock Nestopia and leaves FCEUmm available. The
console selects it for the chosen ROM rather than changing every NES game. Its launch
configuration attaches the emulated Power Glove before the game's detection
sequence begins.

The receiver's shared record and the ROM's packet are different formats: the
record is a 64-byte host interface; the game reads the ten-byte emulated packet.
Their versioning and timing should not be confused with the signed network
protocol used between the two computers.

## Calibration display: native coordinates without a ROM

The optional **VirtualGlove Calibration Test** uses the same 64-byte receiver
record but draws X/Y as a yellow dot on a 4:3 field. It is a separate,
project-owned libretro core and appears under RetroPie's **Ports** list when
chosen during installation. Its launcher selects `super_glove_ball` plus
`lr-powerglove-dot` only for the lifetime of the test, so the Controller uses
the native coordinate path without pretending that an NES ROM is running.

Use it to check center, per-player movement reach, edge behavior, stationary
jitter, brief loss, and recovery. It does not emulate the Power Glove packet,
evaluate finger gestures, or replace live testing in Super Glove Ball.

The build uses a pinned upstream revision and a maintained patch. Licensing,
source provenance, and distribution details are in [Third-party notices](../THIRD_PARTY_NOTICES.md#modified-nestopia-libretro-core).
Follow the [native installation instructions](super-glove-ball-native.md#compare-both-modes-from-emulationstation)
to select the core or return that ROM to FCEUmm.

## What happens when tracking or delivery fails

Lost tracking, missing calibration, the wrong profile, invalid state, or stale
samples produce neutral input. The receiver and native consumer use freshness
checks, including a 250-millisecond stale-state limit. Starting delivery also
requires an armed Controller and an eligible game or deliberate manual context.
These safeguards prevent an old movement from being held indefinitely.

They do not replace good camera placement. Recognition can still be interrupted
when a hand leaves the image or becomes obscured. Keep a conventional controller
available for setup and recovery.

## What the responsiveness evidence means

Deterministic headless comparisons establish input handling in the emulator and
game. They do not include exposure time, inference, the real network, or cabinet
display latency. Live native movement is playable and substantially improved.
The selected MediaPipe 0.10.35 runtime preserved 97.96% continuity on the same
736-frame fast-sweep clip while reducing inference p95 from 60.18 to 46.60 ms
and palm-reacquisition p95 from 149.48 to 120.16 ms versus the former runtime.
A live Dashboard-closed Super Glove Ball trace measured 61.29/91.15 ms
capture-to-send p50/p95 across 3,408 samples, with every receipt correlated and
no trace drops. These are camera-to-network measurements, not complete
physical-hand-to-display latency.

The planned measurement uses one recording containing both the real hand and
screen, plus separate software timings. Only after identifying the dominant
stage should a tuning change be compared against the same baseline. See the
[latency and jitter benchmark](direction-response-benchmark.md). An extra queue
or more smoothing would not be a substitute for measuring the delay.
