# Camera Setup

Your camera is how VirtualGlove sees your hand. This guide helps you choose
a camera, get a clear and responsive picture, and recover quickly when the
camera is disconnected or unavailable.

<img src="images/gestures/v2/pixel-pal-thinking.png" alt="Pixel Pal inspects the camera setup with a magnifying glass" width="150">

Begin with the automatic settings. They work with ordinary USB cameras and are
the best starting point for most families. The advanced frame-rate, reader,
exposure, and gain controls are available when you need to improve a particular
camera or investigate performance; they do not change how gestures are learned
or mapped to games.

## Start here

Use these settings first:

- **Camera:** Automatic
- **Camera frame rate:** Automatic
- **Camera buffers:** 1 buffer
- **Camera reader:** Compatible - OpenCV
- **Exposure behaviour:** Automatic

Connect one ordinary UVC camera, place the whole hand in view, and check the
Dashboard. Change advanced settings only to solve a visible problem or compare
latency.

## Find the best camera settings

Setup includes a Pixel Pal-guided camera test. Choose **Start camera test**, keep
one open hand visible, and follow the centre, corner-sweep, and edge cues. The
test takes about one to two minutes because it repeats the same short movements with each
safe setting supported by the attached camera.

A mirrored live view shows the normal hand landmarks, a centre target, and
camera-edge guides. Use it to keep the whole hand visible during the centre
hold, corner sweeps, and edge check. The view opens only while a candidate is
being measured and closes between candidates and when the test ends. Frames are
displayed temporarily; they are not recorded or saved.

Pixel Pal compares the current settings with supported frame rates, buffering,
camera readers, and automatic-exposure choices. A setting is not recommended if
the requested reader fell back, the requested high frame rate was not actually
delivered, or hand continuity fell materially below the best trial. Among the
remaining choices, lower camera-to-controller age wins.

Controller output is stopped during the test. The original camera settings are
restored before results appear, and nothing changes permanently until you choose
**Use recommended settings**. Choose **Stop test** at any time to restore normal
operation. If the camera disconnects, reconnect it and choose **Stop test**;
Setup restores any pending original settings, restarts normal vision, and then
offers a clean **Start camera test** action. A Controller restart also restores
the exact original settings. The test stores aggregate rates and timings only;
it does not retain camera frames, pictures, or video.

Recommendations belong to the tested physical camera. If the connected camera
changes before saving, Setup asks you to run the test again.

## Camera buffers

Setup can explicitly save **1 buffer** or **2 buffers**. One buffer minimizes
the driver's queue depth; two can provide steadier delivery on some cameras and
hubs. Neither choice creates a software frame queue—VirtualGlove still
keeps only the newest captured frame. Start with one buffer, or use Pixel Pal's
camera test to compare both choices with the attached camera.

## Camera selection

**Automatic** discovers a usable camera when tracking starts. The camera does
not need to be attached during installation; it may be connected later. Setup
refreshes its camera list while the page is open.

Choose a named camera when more than one camera is connected or Automatic picks
the wrong one. A saved camera that is temporarily disconnected stays listed as
unavailable so the Controller does not silently switch devices.

## Frame rate

- **Automatic** prefers 30 fps and accepts the camera driver's usable rate.
- **30 fps** requests the tested gameplay rate.
- **60 fps** is a comparison option for cameras that support it.

An unsupported rate falls back safely. While tracking is active, Setup reports
the actual delivered rate below the camera controls.

## Camera reader

Think of the camera reader as the route a picture takes from the camera into
VirtualGlove:

- **Recommended - OpenCV** works with the widest range of cameras and was the
  smoothest choice in live gameplay. Start here.
- **Engineering comparison - Direct V4L2** talks more directly to compatible
  Linux cameras. It can expose better driver timing and manual controls, but it
  requires a 64-bit, 640×480 MJPEG stream and is not automatically faster. On
  the tested Kiyo Pro, Super Glove Ball felt slower with this route.

If Direct V4L2 is not supported, the Controller returns safely to OpenCV and
reports the fallback. No gesture or calibration is changed.

Direct V4L2 does not change MediaPipe recognition, gestures, calibration, or
controller mappings.

## Exposure and gain

Start with **Automatic**. Brighter images are not always faster: a camera may use
a long exposure in dim light and silently reduce its effective frame rate.

- **Automatic - fixed frame rate** asks a camera that advertises the control to
  preserve frame cadence.
- **Automatic - Razer Kiyo Pro tested** also requests the tested temporary
  HDR-off setting.
- **Manual exposure and gain** is available only with Direct V4L2 and only when
  the camera reports safe limits.

Manual values are camera-specific. Unsupported settings fall back to automatic
exposure and are reported in Setup. Camera automation is restored when tracking
closes. The Razer-specific hardware choice is temporary; repowering the camera
restores its own defaults.

## Lighting and placement

- Light the hand from the front or side, not from a bright window behind it.
- Keep the entire hand, wrist, and intended movement area inside the frame.
- Avoid motion blur by adding room light before increasing gain.
- Keep the camera and playing position consistent with the saved centre and
  movement reach.

Glove Academy may warn about a dark hand or a much brighter background. These
warnings are advisory and do not change camera exposure automatically.

In one matched Kiyo Pro test at manual exposure `78` and gain `96`, reducing a
bright window behind the player improved overall hand detection from 98.73% to
99.57% and cut reacquisitions from two to one. Fast-sweep detection was already
about 98.8% in both clips, and inference time did not change. Treat this as
practical placement guidance rather than a universal camera setting.

The shipped MediaPipe Hands 0.10.35 CPU runtime improves inference and
reacquisition timing independently of camera exposure. Better front lighting
still gives it clearer evidence and more recovery margin; it does not make the
model calculation itself run faster.

The production recognition settings use four CPU inference threads, a `0.35`
landmark-tracking gate, and a `0.45` palm-detection gate. They apply to every
supported camera and normally need no adjustment. Final sustained measurements
found that camera delivery and scheduling were stable; the remaining large
latency tail occurs when MediaPipe must run its palm detector after losing the
tracked hand region. Good framing and lighting help avoid that recovery path.

## Reconnection and recovery

The Controller looks for the saved camera whenever tracking starts. Supported
camera settings are reapplied after a reconnect. The standard Controller
installation includes the recovery helper and `uhubctl`; there is no separate
camera-recovery choice during installation. The helper can recover a stream that
remains wedged even though the camera is still visible to USB. It uses `uhubctl`
only when that tool lists the exact enrolled
hub as supporting per-port power control. In that case, it cycles only the
camera's saved port. It never forces an unsupported hub. When port switching is
unavailable, an identity-checked whole-hub rebind is allowed only if that hub
does not carry networking.

Seeing the camera return in USB is not considered successful recovery. The
helper reports that the USB action has finished, the Controller restarts vision,
and recovery is confirmed only after the worker receives a real video frame.
The camera does not need to be attached during installation; its hub and direct
port are learned on the first healthy use and updated after a move.

Automatic camera selection is the portable behaviour. Per-port cycling depends
on the hub hardware; unsupported hubs continue to use the guarded fallback.

## Quick troubleshooting

- **Camera not listed:** reconnect it, wait a few seconds, and reload Setup.
- **Camera listed but no picture:** stop and restart controller output; if the
  hourglass remains, reconnect the camera or its powered hub.
- **Dark or blurry picture:** improve room lighting, then compare fixed-rate
  automatic exposure.
- **Manual controls unavailable:** return to Automatic or use a camera that
  exposes the required UVC controls.
- **Tracking jumps at an edge:** check framing, centre, and Movement reach before
  changing exposure.
- **Unsure which advanced settings suit a new camera:** run **Find the best
  camera settings** in Setup with your usual lighting and playing position.

For symptom-by-symptom recovery, see the
[Troubleshooting guide](TROUBLESHOOTING.md). For every stored field and installed
path, see the [Configuration reference](CONFIGURATION_REFERENCE.md).
