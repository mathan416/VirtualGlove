# Changelog

This file records user-visible VirtualGlove changes. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories and uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Git remains the
authoritative record for line-level and file-level history.

## [Unreleased]

## [0.4.1] - 2026-09-13

### Added

- Added exact Program 1–10 filename aliases observed in the NES library for
  revision-tagged, alternate-region, and `Robo Warrior` spelling variants.
  These aliases retain the official profile and rapid-fire behavior.

- Added the original Power Glove Programs 1–14 as first-class profiles, with
  their documented movement, finger, wrist, depth, compound-action, rapid-fire,
  centering, and manual-control behavior. Added Mattel's indexed game mappings,
  exact case-insensitive `.nes`, `.zip`, and `.7z` aliases, and per-game rapid
  A/B exceptions without changing Programs A–I or the dedicated game profiles.
- Added validated structured game-registry entries with optional `rapid_a` and
  `rapid_b` switches. Overrides travel with the authenticated game lease and
  are reported read-only in live status; existing string entries remain valid.
- Added numeric Program 1–14 displays to the matrix protocol without renumbering
  existing Program A–I, Bad Street Brawler, or Super Glove Ball codes.

- Added a visual-only Vulcan-salute easter egg to live camera experiences.
  Holding an extended hand with a deliberate middle/ring split briefly shows
  **Live long and prosper** with Pixel Pal, then fades without changing or
  suppressing controller input. It requires a release before rearming, has a
  30-second cooldown, stores no hand data, and announces the phrase politely to
  screen readers.

- Added **Center hand** directly to the Joystick dead-zone camera test. It is
  available only while that panel owns an active safe-practice camera session,
  keeps controller output paused, and redraws the grid from the newly saved
  player center and hand size when centering finishes.

- Added a 3×3 camera grid to the dead-zone test, using the saved calibrated hand
  center and the same translated, full-size bounds as gameplay. A subtle live direction region highlight clears on
  tracking loss or suppressed movement; no labels or palm marker are drawn.
  Moved the camera toggle beside **Use standard size**.

- Added an off-by-default camera test to **Setup → Joystick dead zone**, with its
  own practice lease, mirrored preview, live direction feedback,
  heartbeat/retry handling, and isolated cleanup on stop or page exit.

- Added an optional, resumable **Get ready to play** guide at `/ready`, linked
  from Setup and Dashboard. It rechecks live readiness and uses safe practice
  for essential gestures before an explicit transition to registered-game controls.
- Added separate versioned per-player guide progress, lossless version-5 store
  migration, and a persistent output inhibit that survives interrupted visits.

- Added a read-only Connection Doctor to **Connect to RetroPie**, with progress,
  separate address/service/authentication and runtime checks, plain-language next
  actions, and a sanitized downloadable checklist report. Unsupported game-side
  readiness checks remain explicitly unverified.

### Changed

- Renamed installed RetroPie and UNO Q services, executables, runtime paths,
  configuration directories, bridge methods, protocol identifiers, and managed
  installation metadata from `powerglove-*` to `virtualglove-*`. Upgrades move
  pairing tokens, game registries, launcher settings, and camera enrollment
  forward before retiring the old units and paths into rollback backups. Names
  that specifically identify Mattel's Power Glove or the separate native
  emulation cores remain unchanged.

- Changed the fresh-install startup profile to **Gestures off**. Existing saved
  startup profiles remain unchanged during upgrades.

- Moved **Joystick dead zone** directly below **Players** in Setup so player
  selection, centering, and movement-box adjustment stay together.

- The joystick camera test now previews unsaved slider changes immediately in
  its grid, highlight, and direction pills, using the saved hand center and
  current live palm position. Camera toggles retain the draft; player changes discard
  it. Saving is still required for gameplay, and feedback waits for updated
  worker bounds before returning to saved D-pad output.

- Ordered Setup with separate **Connection and startup** and **Pair with
  RetroPie** sections. **Show statistics** remains at the very bottom, after
  Games, and shares its default-off switch with Dashboard. Recent events is
  retained because it reports recognized gestures such as Glove Zap.
- Joystick dead-zone size now means a chosen width and height fraction of the
  full camera frame, anchored to each player's saved neutral palm center in both
  preview and gameplay. The effective square is at least 1.5 times the saved
  calibrated hand size; near a frame edge it translates inward without clipping
  or shrinking. Live hand size and jitter never make the box breathe. All existing
  numeric choices and player/calibration data remain unchanged, as do native
  Super Glove Ball X/Y calibration and reach.

### Fixed

- Made fresh installations emit only `virtualglove-*` service, executable,
  runtime, and managed-metadata names. Coordinated upgrades migrate existing
  pairing, launcher, game-registry, player, calibration, tuning, Academy, and
  camera-enrollment data before retiring legacy paths into recovery backups.
- Fixed RetroPie upgrades from pre-0.4.1 installations so the bootstrap
  recognizes the existing legacy launcher before asking for a Controller
  address. Package-source preflight now completes before the installer creates
  or migrates VirtualGlove configuration, and existing cabinet hooks are
  validated before that migration begins.
- Stopped legacy systemd path and timer triggers before their services during
  migration, preventing trigger warnings and overlapping old/new helpers.
  Obsolete early-start trial units are retired with the other legacy helpers.
- Refused UNO Q helper migration while a shutdown request is pending. This
  prevents enabling the renamed `PathExists` watcher from halting the board
  halfway through an update.
- Changed engineering Wi-Fi deployment to include and checksum-verify the
  compiled Matrix image, flash it before application restart, require a matched
  firmware handshake, and use administrator access when retiring a root-owned
  legacy application directory.
- Strengthened release-package validation to require every renamed UNO Q and
  RetroPie runtime file and reject legacy service, hook, or executable names.

## [0.4.0-rc.7] - 2026-09-11

### Added

- Added friendly first-install Controller naming with `virtualglove.local` as
  the suggested address, custom-name validation, confirmation, visible LAN
  conflict detection, an explicit unattended option, and upgrade-safe hostname
  preservation. The containerized HTTPS server now uses the approved UNO Q host
  identity rather than a transient App Lab container name.
- Added a persistent per-Controller local certificate authority, HTTPS-only
  public trust-certificate download, automatic named leaf renewal, and guided
  one-time browser trust while retaining physical Matrix fingerprint pairing.
- Added clear installation and troubleshooting guidance for RetroPie systems
  whose Raspbian Buster package source has moved to the legacy archive.
- Rebuilt the optional Engineering Toolkit as a curated, self-checking release
  archive with a dedicated technical guide, repeatable environment setup,
  categorized commands, clean-extraction validation, and resolved-package
  records.

### Changed

- New Controller installations now use `/home/arduino/ArduinoApps/virtualglove`,
  so App Lab creates only `virtualglove-*` containers and networks. An existing
  pre-rebrand installation is stopped without relaunching, has its private data
  copied safely, and is moved into the installer recovery backup only after
  VirtualGlove starts successfully.
- Renamed the Controller's App Lab Compose project and running containers from
  `powerglove-vision-*` to `virtualglove-*`. Upgrades stop and remove the legacy
  project before starting the renamed containers, while protocol identifiers
  remain compatible.
- Extended RetroPie's single-use pairing-code window from two minutes to five
  minutes and clarified that the command must run on the exact console selected
  in Setup when multiple RetroPie systems are online.
- UNO Q release packages now carry checksum-described, precompiled Matrix
  firmware. Ordinary installations use the board's factory OpenOCD support and
  no longer download the Zephyr compiler toolchain. Source builds remain
  available in the full repository.
- RetroPie installation detects the obsolete Buster package host before making
  VirtualGlove changes and tells the operator exactly which source file needs
  repair without silently changing operating-system repositories.
- Removed release building, deployment, documentation generation, firmware
  stamping, and other incomplete repository-maintenance workflows from the
  Engineering Toolkit archive. Added missing direct helpers and kept normal
  installation and calibration documentation free of engineering setup steps.
- Made Toolkit archives reproducible, required side-effect-free help from shell
  tools, verified recorded environment identity, included the Toolkit PDF in
  Controller packages, and added an extracted-package CI workflow smoke test.
- Made zero-jitter motion simulations safe and changed the Toolkit's
  unsmoothed comparison to exercise the real latest-coordinate path.

### Fixed

- Prevented release upgrades from starting App Lab's regenerated legacy
  `powerglove-vision` Compose project while the renamed `virtualglove` project
  still owns its published ports. The installer now stops both possible project
  identities before regeneration, then completes the existing one-stack
  migration to `virtualglove-*`.
- Added a transparent web-specific VirtualGlove logo so the Controller header
  blends with its page background while PDF covers retain the original artwork.
- Fixed clean UNO Q release installation after App Lab startup by explicitly
  preserving the application root while recreating generated Compose services;
  brick mounts can no longer collapse to invalid root-level `/scripts` paths.
- Prevented the release installer from generating a Python bytecode cache inside
  its verified staging tree before applying the installation manifest. RC.7's
  archive was clean, but this runtime cache caused a clean UNO Q installation to
  reject the installer's own generated path. Release packaging now exercises
  setup loading against each extracted package and rejects any staging mutation.
- Made every primary UNO Q download command enter `/home/arduino` before
  saving the installer. This prevents first-time installation from failing when
  the Controller terminal opens in the non-writable `/` directory.
- Corrected Pixel Pal's Extra-Digit Hunt answer from 14 to 15 after a complete
  visual audit found one more six-digit glove in the opening Rock, Paper,
  Scissors table. The documentation check now also rejects six-digit artwork
  that is labelled for accessibility but missing from the hunt manifest.
- Restored complete Python 3.7 release validation: camera-profile recovery and
  backup rotation now use compatible runtime APIs, and affected tests avoid
  newer mock-call conveniences. The release gate now runs the full suite on
  both Python 3.7 and Python 3.12 before packaging.
- Made local HTTPS certificate renewal independent of OpenSSL's version-specific
  hostname-check exit behavior, so a changed Controller IP is always reflected
  in the trusted certificate. Corrected the remaining Python 3.7 Matrix test
  compatibility issue found by the release gate.

## [0.4.0-rc.6] - 2026-09-11

### Changed

- Reworked the repository README into a concise project landing page with a
  clear introduction, feature summary, hardware checklist, seven-step release-
  candidate installation path, first-play guidance, and simpler routes into the
  user and technical documentation. Removed the Extra-Digit Hunt explanation
  from the README while retaining the game in the illustrated guides.
- Added automatic paired-console recovery when a saved IP becomes stale or
  `.local` resolution is unavailable. The Controller now detects missing
  authenticated receiver replies, broadcasts only a signed handshake on each
  connected physical LAN, and resumes with the responder that proves possession
  of the existing pairing key. Controller states are never broadcast, and the
  recovery does not replace or expose the saved key.
- Added the reverse recovery path for RetroPie's registered-game profile renewals.
  A failed saved Controller destination triggers a ROM-free signed discovery
  request; only the paired Controller's request-matched response is accepted before
  the real profile command resumes by unicast. The authenticated address cache is
  bounded, lasts 30 seconds, and never rewrites saved configuration.
- Setup now distinguishes its saved console destination from the active
  authenticated controller link and can download a field-allowlisted system report.
  The report includes useful version, camera, controller, profile, and connection
  health while excluding frames, secrets, player/calibration data, ROM names, and
  network addresses.
- Added a fresh-hardware acceptance checklist covering clean installation, pairing,
  persistence, receiver restart, DHCP/name recovery, camera reconnect, coordinated
  upgrade, and final FCEUmm/native play confirmation.
- Consolidated controller-state cadence, signed handshake maintenance,
  paired-console discovery, registered-game leases, Setup health checks, host
  link sampling, recovery windows, and representative LAN traffic in one
  technical architecture table. The configuration and security references now
  link to that common operational explanation.
- Renamed the public GitHub repository from `PowerGlove-Vision` to
  `VirtualGlove` and updated documentation and installer download sources to
  use the new canonical address. GitHub's old repository links remain usable
  as redirects.
- Clarified that guarded camera recovery and the `uhubctl` package are installed
  automatically by the standard Controller installer. The standalone recovery
  script is retained only for repair and development deployment.
- Simplified the first-time installation language, standardized Glove Academy
  naming, corrected post-rename checkout paths, and clarified that every native
  action required to complete Super Glove Ball has been confirmed in live play.

## [0.4.0-rc.5] - 2026-09-11

### Changed

- Renamed the project and all user-facing product identity from **PowerGlove
  Vision** to **VirtualGlove**, including the application, website, virtual
  controller, documentation, public PDFs, installer packages, screenshots, and
  release artifacts.
- Reworked the existing hand, camera, framing, and target logo into a single
  **VIRTUALGLOVE** wordmark. The Dashboard intentionally retains the quotation
  “I love the Power Glove. It’s so bad.” while its product description now says
  “your camera-only VirtualGlove.”
- Retained compatibility identifiers needed by installed systems and native
  emulation, including the `powerglove_vision` Python namespace, existing
  `/opt/powerglove` and `/etc/powerglove` paths, service/script filenames,
  protocol version, and `lr-nestopia-powerglove` core name. These identifiers
  continue to upgrade in place and are not presented as the product name.
- Renamed new portable hand-setup exports to
  `<player>-virtualglove-hand-setup.json` with format
  `virtualglove-hand-setup` version 4. Existing `powerglove-hand-setup`
  version-2 and version-3 files remain importable.

## [0.4.0-rc.4] - 2026-09-10

### Added

- Added five context-specific Pixel Pal stances for coaching, play, inspection,
  safety, and success. The website and friendly guides now choose his pose by
  purpose while preserving the existing welcome and Glove Master trophy art.
- Added a per-player square center-box control for FCEUmm joystick movement,
  including all four diagonals, immediate center release, live direction feedback,
  and automatic neutral-jitter protection.

- Added an Engineering Journey that records the one-week development process,
  measurement discipline, CPU/GPU investigations, discarded movement paths,
  reliability work, and lessons behind the current architecture.
- Added the complete GNU GPL version 2 licence text required by the distributed
  Nestopia-derived patch and clarified exactly which third-party components are
  bundled, built on the target, installed from Debian, or supplied by RetroPie.
- Added an on-demand, mirrored live view with centre and edge guides to Pixel
  Pal's camera-settings test so players can verify hand placement during sweeps.
- Added Pixel Pal's **Find the best camera settings** wizard to Setup. It safely
  compares the current camera configuration with supported reader, frame-rate,
  buffer, and exposure choices; rejects reader fallbacks and unsupported rates;
  protects hand continuity before ranking latency; and saves only an accepted
  recommendation for the same physical camera. Trials retain aggregate timing
  only—never video or images—and restore the exact original configuration after
  completion, cancellation, or an interrupted Controller restart.
- Added a persistent **Stop test** recovery control to the camera wizard. It
  remains available after a camera disconnect, restores any pending exact
  pre-test configuration, restarts normal vision, and returns the wizard to a
  clean state so the camera test can be started again.
- Added an explicit one- or two-buffer camera setting to Setup. Manual camera
  saves and Pixel Pal's camera recommendation now expose the same validated
  capture-buffer choice.

### Changed

- Completed the MediaPipe CPU-pipeline refinement and froze the validated
  production defaults: OpenCV with thread isolation, one requested buffer,
  30-fps-first negotiation, four inference threads, tracking confidence `0.35`,
  palm-detection confidence `0.45`, a 2.25 search region, direction-aware
  fast-sweep tracking, and Latest-coordinate native X/Y.
- Added detector-context attribution to the output-paused camera benchmark.
  A final sustained run separated camera dequeue, MJPEG decode, inference
  pickup, the preceding frame, palm detection, recovery, post-graph work, and
  Linux scheduling. Ordinary landmark tracking measured about 37 ms median;
  palm detection/reacquisition measured about 105 ms median. Camera delivery,
  scheduling, recognition output, and transport were not the source of the
  detector tail.
- Rejected lower `0.10` and `0.20` tracking-confidence gates. They did not
  prevent any fast-sweep detector entries and increased reacquisition p95 from
  about 102 ms at `0.35` to 126-128 ms. A broader clip likewise found no useful
  recovery trade-off.
- Extended process-isolated capture research to OpenCV as well as Direct V4L2.
  Both variants retain one coherent latest frame and report an explicit fallback;
  matched live tests still selected thread-isolated OpenCV for production.
- Made Controller restarts terminate and reap the complete worker process group,
  including its private `uv`, Python, and camera-owning descendants, before a
  replacement worker starts.

- Replaced positional activation/release hysteresis with the original-style
  nine-region layout: center, four cardinal directions, and four diagonals. Every
  fresh position is classified independently; native Super Glove Ball X/Y,
  Menu Guard, tracking-loss safety, and Program-specific mappings are unchanged.
- Upgraded the player store to version 5 and portable hand-setup backups to
  version 3. Older stores and version-2 backups migrate the largest directional
  activation value into the new scalar center box and discard obsolete releases.
  Positional directions are no longer offered as gesture-personalization channels.

- Reworked Architecture as a current-system reference and moved historical
  movement, runtime, GPU, and reacquisition discussion into Engineering Journey.
- Consolidated the Programs A–I handbook into the Gameplay Guide, reordered its
  discovery flow, and retired the redundant standalone Programs PDF.
- Updated Installation, Camera, Configuration, Native Emulation, and Super
  Glove Ball Native guides for the current OpenCV default, optional Direct V4L2
  path, one/two-buffer choice, Pixel Pal camera test, 180 ms X/Y-only brief-loss
  hold, and MediaPipe 0.10.35 CPU runtime. First-time setup now emphasizes safe
  defaults and links to detail instead of presenting driver choices as required.
- Extended only native continuous X/Y's brief missed-observation hold from 120
  to 180 ms, covering roughly one additional MediaPipe result during an extreme
  corner-to-corner sweep. Buttons, finger states, depth, roll, and D-pad output
  still release on the first missed native observation. MediaPipe tracking confidence,
  direction-aware search, and the validated reacquisition logic are unchanged.

- Extended the output-paused camera benchmark for sustained UNO Q runs. It now
  separates driver dequeue age, MJPEG decode, recognition pickup, graph time,
  and post-graph work; learns camera sequence-counter cadence; records compact
  correlated tail events; and can attribute palm-versus-landmark paths without
  retaining images.
- Added a three-thread research lane and rejected it after a live four/three/four
  comparison. Three threads produced fewer coordinate results and higher normal
  latency without improving end-to-end p95, so the validated four-thread
  production setting remains unchanged.
- Added a benchmark-only process-isolated camera lane with Linux task-scheduler
  counters. A 90-second A/B/A comparison and five-minute soak showed that it
  continued draining frames through long MediaPipe palm-search calls, reduced
  the worst observed coordinate age from 303–327 ms to 239 ms, and completed
  without a camera error. It is not yet a production capture mode.
- Added process-isolated Direct V4L2 as an engineering comparison. It owns one
  replaceable shared frame, reports child failure repeatedly so existing
  recovery can act, restores manual exposure in the camera-owning process, and
  falls back to threaded OpenCV when startup fails. Matched live Super Glove
  Ball tests selected OpenCV with thread isolation as the production default:
  it felt faster, remained playable through fast sweeps, and recovered quickly
  after intentional departures from the camera view.
- Matched the isolated reader to the proven camera lifecycle by treating a
  camera-marked invalid MJPEG frame as transient. Hardware validation confirmed
  process startup, manual exposure 78/gain 96, 569 advancing driver frames over
  ten seconds, graceful shutdown, descriptor release, and automatic-exposure
  restoration. A deliberately killed child can still wedge this Kiyo/hub at the
  USB level, so destructive crash injection is not part of routine validation.
- Promoted the validated direction-aware fast-sweep search to standard
  MediaPipe behavior. Removed its Setup checkbox and guarded save endpoint;
  older `directional_search` device-file values are now harmlessly ignored.
- Renamed the packaged CPU runtime from the misleading `powerglove.gpu2` local
  version to `powerglove.cpu1`. Its selected graph and behavior remain the same;
  the new name makes clear that production inference uses XNNPACK on the CPU.
- Corrected Setup's Controller output flag so an armed Controller waiting for a
  game is shown as ready instead of falsely reporting **Receiver unavailable**.
  Genuine delivery failure remains red during an active game context.
- Made camera recovery refuse a whole-hub driver rebind when the enrolled hub
  also carries a network interface. Capability-confirmed per-port power cycling
  remains allowed; unsupported network-bearing hubs now fail safely instead of
  disconnecting the Controller's Ethernet path.
- Made worker startup probe its retained `uv` environment offline first. A
  complete cache now restarts without Internet access, while a new or incomplete
  installation automatically retains online dependency resolution.

## [0.4.0-rc.3] - 2026-09-09

### Added

- Added a separate, version-matched VirtualGlove Engineering Tools source
  archive for protocol traces, replay analysis, benchmarks, GPU experiments,
  soak tests, and maintainer build tools. It contains no ROMs, recordings,
  credentials, device data, cached models, or compiled cores.
- Added an optional, ROM-free **VirtualGlove Calibration Test** to RetroPie's
  Ports list. Its separately built `lr-powerglove-dot` core displays the same
  guarded native X/Y used by Super Glove Ball, automatically holds and releases
  a native test profile, and gives players a simple center, reach, edge,
  tracking-loss, and recovery check without changing any game's emulator.
- Added a camera-free post-inference benchmark with repeated statistics-off,
  statistics-on, and statistics-off lanes. It measures established-session UDP
  transmission, Dashboard housekeeping, full-iteration tails, and newest-only
  publication under a deliberately slow status consumer.
- Added capture-timestamp tracking-loss and reacquisition telemetry. Diagnostics
  now separate the duration since the last detected hand, the observed missing
  span, the recovery inference time, and the longest loss instead of inferring
  recovery cost from worker-loop timing.
- Added a production-matched, user-paced fast-sweep recorder and a replay-only
  zero/one-frame directional-search recovery comparison. Direct V4L2 captures
  retain their actual buffer, exposure, and gain settings, restore camera
  automation on exit, and retry brief invalid-frame gaps without abandoning the
  recording.

### Changed

- Replaced the former MediaPipe 0.10.18 package with MediaPipe Hands 0.10.35 as
  the sole CPU recognition runtime after matched replay and live Super Glove
  Ball validation. Gesture rules, calibration, Latest-coordinate movement, and
  controller mappings are unchanged. The rebuilt ARM64 wheel removes unused
  JAX/JAXLIB dependency declarations and pins headless OpenCV 4.11.0.86.
- Focused ordinary Controller and RetroPie release packages on production code
  and end-user calibration, status, recovery, and emulator-setup tools. The full
  engineering suite remains in Git and on development deployments but is no
  longer installed for first-time users.
- Made the active emulator part of RetroPie's authenticated, renewable game
  heartbeat. Only the exact `super_glove_ball` plus
  `lr-nestopia-powerglove` pairing selects native packets; FCEUmm and every
  other or unknown core use joystick output. Changing cores is treated as a
  controller transition so held native or joystick state cannot leak between
  modes.
- Coordinated guarded camera recovery with the vision worker: the worker closes
  the camera before the enrolled hub reset, waits for the helper result, then
  reopens and retries only after its cooldown. Recovery applies to any active
  gesture profile, whether output is native or joystick. A headless Kiyo Pro
  test confirmed the guarded stop/reset/restart sequence and USB
  re-enumeration, but the camera still required a physical reconnect before it
  produced frames; USB presence alone is not reported as stream recovery.
- Added capability-detected camera-port power cycling through `uhubctl`. The
  helper targets only the enrolled camera's exact port when the hub is listed as
  per-port switchable and never forces unsupported hardware. Older enrollment
  files and unsupported hubs retain the identity-checked whole-hub rebind.
  Helper completion now means only that the USB action ended; recovery is
  confirmed separately after the restarted worker receives a real frame.
- Kept Dashboard work out of the controller-critical boundary. Tuning state is
  resolved before MediaPipe inference, gameplay state is sent before periodic
  handshake maintenance, browser status preparation is limited to 10 Hz while
  control transitions publish immediately, and preview mirroring no longer
  selects a slower MediaPipe preparation path.
- Bounded handshake reply processing to two datagrams per frame and replaced a
  recursive controller-state copy with an explicit signed-wire mapping. These
  changes preserve authenticated delivery and receiver-restart recovery.
- Aligned the example Controller configuration with the shipped four-thread,
  0.35 tracking-confidence and 2.25 search-area defaults.

- Made Latest coordinate the only live Super Glove Ball native X/Y behavior.
  Removed the Dashboard movement selector and its restart endpoint; older saved
  bounded-mode values are ignored, while historical benchmark tooling remains
  available for engineering comparison.
- Reorganized Setup into shorter, action-first sections. Tracking and controller
  output now use the same red, grey, and green status flags as connection checks;
  the console-check age and gameplay caveat remain visible without the redundant
  color legend.
- Put player naming controls before their explanation, summarized what each
  player and hand-setup backup contains, and named downloaded backups after the
  player, such as `alex-powerglove-hand-setup.json`.
- Separated Camera from Connection and startup, moved pairing-key and live camera
  status text beside their related controls, and moved joystick dead-zone help
  below its controls.
- Added a focused Camera guide covering automatic selection, frame rate, capture
  reader, exposure, lighting, reconnection, and troubleshooting.

### Validation

- Replayed the same 736-frame fast-sweep clip through both packaged runtimes.
  Detection continuity and all 15 one-frame misses were identical at 97.96%,
  while MediaPipe 0.10.35 reduced overall inference p95 from 60.18 ms to
  46.60 ms and palm-reacquisition p95 from 149.48 ms to 120.16 ms. A live
  Super Glove Ball trace delivered all 3,408 samples, improved capture-to-send
  p95 from 126.84 ms to 91.16 ms, and had zero trace drops. A ten-minute
  output-paused soak completed without errors, reached 61.7 °C at its hottest
  reported zone, and settled at a stable memory plateau.
- Corrected the saved-clip loss interpretation after frame-level review. Its
  nine-frame run is the scripted hand-removal cue, while the selected fast-sweep
  lane detected 91 of 92 frames and missed only the exact cue-boundary frame.
  Replay reports now label missing runs with frame ranges and cue names.
- Replayed the saved 402-frame sweep with Dashboard preview closed and open.
  Both lanes used identical fused preprocessing and 96.52% detection continuity;
  inference p95 was 4.70 ms closed and 4.65 ms open on the development Mac.
- A 100,000-iteration synthetic soak kept signed UDP send p95 at 0.0179 ms in
  all three off/on/off lanes. A deliberately 5 ms status consumer did not block
  controller sends because pending Dashboard snapshots were replaced newest-only.
- Replayed a current-settings Kiyo Pro fast-sweep clip through the production
  four-thread lane. The selected `2.25` search area, `0.35` tracking confidence,
  and `0.55` palm-detection confidence retained 98.82% fast-sweep detection.
  Larger search areas, lower detection thresholds, and a one-frame search-offset
  carry did not improve the moving cue, so immediate reset and current defaults
  remain unchanged.
- A matched exposure-78/gain-96 lighting comparison improved overall detection
  continuity from 98.73% to 99.57%, reduced missing frames from three to one,
  and reduced reacquisitions from two to one. Fast-sweep detection remained
  effectively tied at 98.82% and 98.84%, while inference stayed near 35 ms
  median and 49 ms p95. Better front lighting adds tracking margin but does not
  make MediaPipe inference itself faster.

## [0.4.0-rc.1] - 2026-09-08

The first public 0.4.0 release candidate combines the validated Latest-coordinate
native movement path with lower-overhead capture, clearer camera selection,
portable exposure defaults, and guarded recovery. It is suitable for interested
users to install and test, while remaining a prerelease rather than the final
0.4.0 release.

### Changed

- Replaced Setup's free-form camera number with a live dropdown containing
  Automatic and the currently discovered usable cameras. The list refreshes
  while Setup is open, excludes codec-only video devices, and keeps a saved but
  temporarily disconnected selection visible instead of silently changing it.

- Added an optional capability-checked Manual exposure and gain setting for the
  Direct V4L2 camera path. Automatic remains the portable default. The worker
  applies controls through the active stream, reports requested and actual
  values and supported ranges, falls back explicitly when unsupported, and
  restores automatic exposure when vision closes. A matched Kiyo Pro play test
  selected exposure `78` and gain `96` for this Controller because continuity
  was slightly better than Automatic while measured latency was unchanged.

- Hardened camera recovery by distinguishing a healthy-camera enrollment from
  a sustained stream-recovery request. The allowlisted hub can now receive one
  guarded reset when video is wedged even if the camera still appears in USB
  enumeration; ordinary reconnects continue to update the saved camera-to-hub
  association.

- Promoted MediaPipe's `2.25` next-frame hand search area and `0.35` tracking
  confidence as the reproducible defaults. The larger search area recovered five
  of nine missed fast-sweep frames without material latency or false-activation
  cost. Palm-confidence changes, every-frame palm detection, and the full
  landmark model did not pass their latency/continuity gates and remain
  benchmark evidence rather than gameplay modes.

- Added advance preparation for the next physical hand-to-display latency session:
  a privacy-safe read-only two-device preflight, a short framing/smoke protocol,
  a reversible Controller/receiver trace manager, and contact-sheet-based video
  review. These tools leave movement math unchanged and cannot treat terminal cue
  time or unrelated device clocks as physical latency evidence.

- Moved Dashboard status publication onto a latest-only worker. Changed
  controller state is submitted immediately; routine detailed gesture and
  controller feedback is limited to about 10 Hz, and rolling percentile
  summaries to 2 Hz, only while **Show statistics** is enabled. Ordinary camera
  preview no longer requests landmark diagnostic payloads merely to draw the
  already-available skeleton.

- Added an opt-in direct V4L2 capture backend for Linux 64-bit, 640×480 MJPEG
  cameras. It drains to the newest driver buffer, retains a valid monotonic
  camera timestamp, and automatically reopens the compatible OpenCV path if the
  camera or negotiated format is unsupported.

- Added capability-detected low-latency exposure choices. Standard UVC controls
  are queried before any write; supported cameras retain automatic exposure but
  can disable exposure-driven frame-rate variation. The Kiyo Pro choice also
  requests the existing USB-identity-checked volatile HDR-off mode.

- Added a configuration-only lean MediaPipe Hands comparison that requests image
  landmarks without world-landmark or handedness output streams. The full graph
  remains the production default until matched Controller tests prove the lean
  output set is faster without recognition regressions.

- Consolidated overlapping documentation by purpose. Third-party licensing,
  runtime provenance, asset origins, and modified-core distribution now share
  one notice; screenshot and web-art production moved into Contributing; the
  early-start repair material moved into the Configuration Reference; and the
  September 6 Setup review was folded into this release history.

- The September 6 review covered Setup routes, persistence, worker controls,
  pairing, signed delivery, installation manifests, player backups, hostname
  refresh, networking indication, and web-module separation. Automated checks,
  browser interaction tests, package verification, and live paired-device checks
  passed for the recorded fixes. Its then-outstanding camera-to-display latency
  work is now tracked in the movement evidence documents rather than a separate
  review file.

- Regenerated the complete 19-guide PDF set and Controller Help from the
  consolidated Markdown structure.

- Added end-to-end architecture and timing-boundary diagrams showing the shared
  camera and MediaPipe front end, authenticated Controller-to-RetroPie delivery,
  the FCEUmm and custom Nestopia paths, and the final game/display response.
  Camera benchmark results now state exactly which part of that chain each test
  measured and what remained outside it.

### Validation

- The final release-candidate suite passes 535 tests with one expected
  Linux-specific `IP_PKTINFO` integration skip on macOS. Documentation audits
  cover all 19 Markdown guides and matching PDFs, and browser interaction tests
  cover live camera discovery, camera selection, exposure choices, and saved
  Setup behavior.

- A live Razer Kiyo Pro test accepted the direct V4L2 path at 640×480 MJPEG
  and 30 fps. The driver supplied monotonic timestamps and advancing sequence
  numbers; a representative fresh sample measured about 1.25 ms from the
  driver timestamp to userspace dequeue, with the expected 33.3 ms capture
  cadence. Direct V4L2 remains optional because other Linux cameras and drivers
  may negotiate differently.

- The output-paused lean-graph comparison was not promoted. Against the same
  direct-capture setup, its median inference time improved only from about
  43.9 ms to 43.2 ms, while p95 sample age increased from about 108.5 ms to
  114.6 ms. The complete graph therefore remains the default.

## 0.4.0 development baseline — September 7, 2026

This unpublished development baseline is included in `v0.4.0-rc.1`. It promotes
the native-movement efficiency work validated after the
0.3.2 release candidates. The shared gesture mappings and FCEUmm behavior remain
compatible; the principal change is a lower-latency, more precise MediaPipe path
for native Super Glove Ball X/Y.

### Added

- Added Automatic, 30 fps, and 60 fps camera-rate choices under Setup's advanced
  camera settings. Automatic tries the tested 30-fps path first, falls back to a
  driver-selected usable rate, and reports the live negotiated rate.

- Added an optional **Show statistics** preference to Dashboard and Setup. It is
  off by default, stored only in the browser, and stops the page from reading,
  rendering, or retaining detailed controller, axes, finger, performance, and
  recent-event fields while disabled.

- Added native trace evidence for raw MediaPipe observations, detection gaps,
  recovery decisions, and one-result confirmations. The analyzer can now review
  ordinary Latest-coordinate traces without enabling optical-flow diagnostics.

### Changed

- Made **Latest coordinate** the production native X/Y default. Continuous
  tracking publishes each newest valid, reach-clamped MediaPipe coordinate
  directly. **Bounded speed curve** remains available as an explicit comparison.

- Changed the Controller baseline to four MediaPipe inference threads, a `0.40`
  tracking-confidence threshold, and 30-fps-first camera negotiation after
  matched live tests. New installations receive these values; saved device
  settings remain preserved during updates.

- Moved preview landmark drawing, status text, downscaling, and JPEG encoding off
  the inference thread. Gameplay previews use a 320×240 latest-only copy while
  Academy and tuning retain full-size visual feedback. Superseded preview work is
  discarded instead of delaying controller delivery.

- Avoided calculating unused experimental palm anchors during ordinary gameplay.
  Diagnostic runs still expose the complete candidate set for comparison.

- Preserved a player's valid comfortable-reach spans when **Center hand** updates
  neutral pose and jitter. If a moved center makes the saved endpoints unsafe,
  the mapping falls back to the full camera field instead of saving invalid reach.

### Fixed

- Prevented the backward-then-forward Robo-Glove jump seen after brief MediaPipe
  reacquisition. Latest-coordinate mode now accepts strongly aligned forward
  recovery immediately, but holds one contradictory or unusually distant
  non-forward result until the next fresh measurement. It does not predict,
  smooth, queue, or overshoot continuous movement.

- Ensured the newest captured frame and its capture timestamp remain authoritative
  through inference, freshness checks, native mapping, tracing, and transmission.

- Corrected the staggered-tracker benchmark to compare matched one-by-four and
  two-by-two CPU lanes using real sidecar capture timestamps. The staggered lane
  was rejected because it increased source age, reduced continuity, and produced
  a much larger coordinate jump.

- Preserved advanced measured device settings when Setup saves ordinary connection
  or camera fields instead of reconstructing a smaller configuration document.

### Validation

- The complete Python suite passes 496 tests with one expected Linux-specific
  skip. Browser interaction coverage includes camera-rate persistence and the
  statistics preference's default-off, safe-rendering, cross-tab, and no-work
  behavior.

- Live Super Glove Ball tracing measured about 65 ms median camera-to-coordinate
  age. In the confirmation window, five strongly forward recoveries passed
  immediately and the new guard inserted no unnecessary holds. The player
  reported the tightest, most hand-attached response reached during testing.

- The rejected staggered-tracker comparison measured 20.23 Hz and 45.64 ms p95
  source age for the one-by-four baseline versus 21.13 Hz and 66.03 ms for the
  two-by-two lane; detection continuity fell from 99.14% to 98.09% and maximum
  coordinate step rose from 0.0407 to 0.3447.

- An isolated Adreno GPU delegate experiment remains non-production: the tested
  MediaPipe Tasks graph was substantially slower than the proven CPU MediaPipe
  Hands path. Version 0.4.0 ships no custom GPU runtime.

## [0.3.2-rc.8] - 2026-09-07

Changes since rc.7: per-player movement reach, selectable latest/bounded native
X/Y, corrected capture timing and landmark validity, edge-safe recovery, lower
native publication latency, and isolated acceleration research tools. The
project base version remains 0.3.2. This is a prerelease.

### Added

- Added a separate Glove Academy **Movement reach** editor for the active player.
  It exposes left, right, up, and down normalized spans, reports tracking-area
  dimensions and aspect ratio, saves only those four fields, and can restore the
  full-camera mapping without changing center, gestures, or lesson progress.

- Added Dashboard selection between **Bounded speed curve** and **Latest
  coordinate** for native Super Glove Ball X/Y. Both modes use the same MediaPipe
  observations, calibration, reach mapping, and safety behavior.

- Added a four-lane native movement comparison for version-2 vision replay reports. It compares the former overshooting experiment, a safely capped error-driven reference, the bounded speed curve, and direct latest coordinates; a deterministic 27-candidate sweep reports jitter, lag, medium response, fast pickup, reversals, overshoot, continuity, and source age when available.

- Added output-paused benchmarks for palm-anchor stability, mirrored-frame
  preprocessing, one/two/four inference threads, tracking confidence, two
  staggered trackers, and MediaPipe Tasks live-stream CPU/GPU experiments.
  These tools do not create a production GPU mode or change gameplay output.

- Prepared optional per-frame motion traces separating recognized, flow, selected and filtered coordinates, including source freshness and fallback reasons. Added an offline saved-sample review and an actual-engine smoothing step model; the model is not a physical latency measurement.

- Added `analyze-motion-trace.py` and `compare-motion-matrix.py` for normalized movement classes, selected-versus-filtered error, settling estimates, source-age distributions, fallback reasons, and tracking-loss counts. Ran the six trace-only smoothing configurations on the UNO with zero dropped trace records and restored the live setting afterward.

- Added Setup → Joystick dead zone: a per-player size slider with automatic half-distance release, live direction indicators, and a standard-size preset. Saves update all four digital direction thresholds while preserving center, native reach and other gestures. Advanced directional pairs remain in Glove Academy.

- Added an optional UNO Q test workflow for the cabinet's installed dot core, dot-labeled guided status sessions, and a read-only native-state probe for validity, loss/recovery and coordinate ranges. MediaPipe, controller output and game defaults remain unchanged; physical comparison is pending.

- Benchmarked Kiyo Pro capture on UNO Q and added an opt-in 640×480 MJPEG/two-buffer/volatile-HDR-off candidate, which delivered 59.7–59.8 fps in isolated capture repeats. Higher 720p decoding costs ruled out copying the Pi resolution. Inference threads are unchanged; recognition-under-load and physical latency validation remain pending.

- Ported optional per-player comfortable reach spans from the Raspberry Pi version. Both MediaPipe response modes map asymmetric reach to the screen edges, player backups preserve spans, and re-centering clears them. Added a guided, output-paused calibration helper using raw palm measurements in practice mode. Camera defaults and inference threads are unchanged pending UNO Q measurements.

- Added and evaluated an experimental Super Glove Ball optical-flow path. Live
  testing found it jerky and unreliable, so it is now archived as research code
  and historical trace support rather than offered as a runtime option.

### Fixed

- Restored Python 3.7 compatibility in historical trace and browser-support
  tools and the optional capture trace's thread identifier. The capture-thread
  test also allows heavily loaded CI runners more scheduling time. These changes
  do not affect production capture timing or controller output.

- Native speed and freshness calculations now use the selected camera frame's
  capture timestamp instead of inference-start time. Invalid or non-finite
  landmark geometry is rejected before mapping, while MediaPipe's handedness
  score is no longer misrepresented as a position-confidence score.

- Both native X/Y modes clamp their input to the active player's calibrated
  reach before response processing. Leaving an edge pins the Robo-Glove there
  without building hidden off-screen filter state; tracking recovery starts
  from the first fresh clamped coordinate.

- Reworked bounded X/Y as one coherent vector response with an elliptical
  calibrated-noise region. Small axis noise no longer causes independent snaps;
  meaningful reversals are immediate, and stops settle inside the noise region
  on the first fresh result and exactly by the next.

- For native Super Glove Ball packets, the RetroPie receiver now publishes the
  native state before updating the unrelated virtual gamepad. Correlated traces
  report socket-return-to-native-publication and native-write time separately.

- Made MediaPipe Hands the sole live coordinate authority for native Super Glove
  Ball X/Y. The bounded curve and direct-latest mode affect only coordinate
  response; FCEUmm and gesture recognition are unchanged.

- Prevented brief MediaPipe dropouts from making the native glove jump through
  neutral and back. The last X/Y can be held for up to 120 ms while action,
  finger, depth, roll, and D-pad state releases immediately; sustained loss still
  neutralizes the complete native sample.

- Corrected the experimental optical-flow Dashboard marker to use the full preview dimensions instead of the downscaled 320-pixel work image, eliminating its upper-left visual offset.

- Replaced native Super Glove Ball's error-driven catch-up and optional extrapolation with a calibrated-reach speed curve. Resting jitter uses a per-player noise floor, deliberate movement becomes progressively more direct, and stops or reversals accept the newest measurement immediately. Compatibility settings above `1.00` can no longer overshoot.

- Pairing now reports success only after RetroPie answers a signed controller handshake with the newly installed token. This catches a copied-but-unusable token while keeping controller arming and actual emulator input as separate checks.

- Experimental X/Y now falls back directly to fresh, confident MediaPipe coordinates when source-to-current flow correction fails or exceeds its budget. Failed flow is cleared, fallback reasons are reported separately, and the original 250 ms recognition freshness limit remains enforced.

- Bound experimental X/Y correction to one checked source-to-current flow step on smaller images, and dispatch the next recognition job before correction. Added correction/pickup/failure diagnostics and a synthetic before/after benchmark. The original MediaPipe path remains the default; live recognition and physical latency validation are pending.

- Restrict UNO host mDNS to detected physical network interfaces during host setup. The test UNO advertised Docker bridges and renamed itself to `ArduIain-2.local` after a conflict during container restarts, breaking profile heartbeat delivery. The backed-up interface correction restored the original hostname and automatic game-profile recovery across a verified app restart.

- Dashboard Center hand and Start controller clicks now survive status refreshes in Safari/WebKit. Controller requests stay disabled while pending, and centering guidance names the selected player beside the controls. Request feedback is announced and displayed beside those controls.

### Changed

- Kept the calibration-compatible five-point palm average as the production
  anchor while exposing four candidate anchors to replay analysis. A different
  anchor must prove at least 25% less pose-induced movement, retain at least 99%
  of deliberate travel, and preserve continuity before it can replace the
  existing coordinate contract.

- Cached expensive percentile telemetry at 2 Hz while preserving per-inference
  recognition state and controller publication. The Controller supervisor now
  passes its validated one, two, or four-thread choice explicitly; the tested
  default remains two.

- Corrected the bounded native curve for the proven MediaPipe backend's measured
  9–10 Hz cadence. The previous 60 Hz follow reference converted the configured
  `0.70` slow-follow weight to nearly `1.00` at runtime, making ordinary native
  X/Y visibly step between raw landmarks. Saturated `1.0` jitter measurements in
  otherwise reusable calibration files now fall back to the small fixed noise
  floor instead of producing a large dead zone and jump.

- Added explicit `native_xy_source` diagnostics for `mediapipe` and `inactive`,
  plus `native_xy_mode` diagnostics for `bounded` and `latest`. Both modes retain
  the normal MediaPipe landmark preview.

- Synchronized the architecture, installation, security, troubleshooting, command reference, built-in Help, README and PDF editions with the asynchronous movement path, comfortable reach, Kiyo capture candidate, per-player joystick dead zone, motion-analysis tools and post-pairing token verification. Standardized new user-facing diagnostic titles on **VirtualGlove Controller** while retaining literal UNO Q filenames and hardware references.

- Added an optional experimental-only X/Y smoothing boost override. The UNO medium-jump trial uses 8 instead of 4, lowering the per-axis immediate-response threshold from roughly .075 to .0375 camera units without changing synchronous tracking or reach calibration.

- Previously added an experimental-only `motion_coordinate_max` cap for controlled extrapolation tests. The exploratory UNO setting used cap 1.30 with boost 15 and minimum smoothing 0.70. That experiment established the stop/reversal risk and is superseded by the bounded speed curve above; retained configuration fields no longer permit overshoot.

- Moved player creation, renaming, deletion, and hand-setup backup/restore into Setup → Players. Academy and Dashboard offer compact selectors for the same Controller-wide active player. Dashboard places Player before Active profile and combines game name and session status in one Game card.

- Glove Academy player selection now immediately loads sensitivity, lesson progress, and the player’s saved center. Removed the separate Use player and Reuse my saved center buttons. Players without a saved center still need Center hand; switching keeps controller output paused, and backup-import calibration reuse remains an explicit choice.

- Renamed the explicit centering action to **Center hand** throughout Dashboard, Glove Academy, player settings, personalization, and maintained instructions. Centering continues to save only to the selected player; switching players during a sample prevents it being saved to the new player.

### Validation

- A live Super Glove Ball status run with the Dashboard closed measured 96.5%
  detected samples, 65.4 ms median and 76.2 ms p95 sample age, 52.2 ms median
  and 58.3 ms p95 MediaPipe inference, 2 ms p95 send work, and about 16 distinct
  native updates per second. The player reported that control was improving;
  this is not yet the synchronized physical hand-to-display acceptance test.

- The UNO Q's Adreno 702 was reached through EGL/OpenGL ES and a custom isolated
  MediaPipe Tasks build created a TensorFlow Lite GPU delegate. That first heavy
  Tasks graph measured about 664 ms warm p50 versus about 207 ms for the same
  Tasks path on CPU, far slower than the proven MediaPipe Hands path. The wheel
  and temporary runtime changes are not in this release; the Controller was
  restored to its clean CPU image. GPU capability is confirmed, while a lean
  GPU palm/landmark path remains untested.

- Confirmed the tested cabinet accepted the newly paired token and subsequently delivered Controller input to a running game. The pairing-complete signal remains deliberately scoped to receiver authentication; the follow-on game test establishes the rest of this installation's path.

The remaining release gate is a synchronized high-frame-rate recording of the
physical hand and display. Software-stage measurements cannot establish camera
exposure, emulator/display delay, or the complete hand-to-screen result.

## [0.3.2-rc.7] - 2026-09-06

Changes since rc.6: guided Setup pairing, networking indicators, refreshed guides and screenshots, and opt-in latency measurement tools. The project base version remains 0.3.2.

### Changed

- Gave the Security network-exposure table dedicated column widths so port numbers stay intact, with less space assigned to Boundary. Refreshed every documented application screenshot from current templates using isolated sample data and an omitted-camera placeholder; added a repeatable capture script and rebuilt the affected PDF editions.

- Pairing now releases the physical approval-PIN display after the submitted request succeeds or fails, allowing the normal matrix display to resume without waiting for the authorization timer. Idle animation still respects On, Dim, or Off. Setup now serves directly at `/setup`; removed the page-revision redirect and link rewriting while retaining the shared favicon and compatibility with old bookmarks. Refreshed Setup screenshots and maintained guides.

- Fixed a Safari/WebKit pairing click failure caused by replacing button text during the half-second refresh. Pairing now brings a dedicated progress panel, completion, and errors into view; missing credentials receive explicit guidance, and live announcements are no longer inside a busy region. Verified delayed mouse clicks and progress feedback in WebKit and Chrome.

- Replaced Setup pairing with three inline steps using the saved console: method selection, physical Controller confirmation, and RetroPie credentials. Retained one-time-code and SSH-password methods, added expiry/retry guidance and secret clearing, renamed the connection button to Save settings, and removed duplicate Controller/power actions from Setup. Pairing APIs and server security checks are unchanged.

- Ordered Help user manuals as This console, Game and gesture guide, Programs A-I, Matrix display guide, Build your own, Installation and setup, and Troubleshooting by symptom. Kept the native-emulation introduction beside the Super Glove Ball compatibility record in Technical documentation. Unified browser-tab icon selection around one versioned multi-size ICO shared by Setup and every other page. The temporary Setup page-revision workaround has since been removed; the plain Setup URL is used throughout.

- Shifted the idle glove’s bottom two wrist rows one pixel right, including the cuff entrance and wrist spark. Refreshed the simulated animation and manual illustrations; this change requires a matrix firmware update. Added versioned website icon URLs to refresh cached icons, including Setup.

- Renamed the fourth connection marker to Networking and extended its host check to physical Wi-Fi or Ethernet, including USB dock Ethernet. Virtual interfaces are excluded; legacy telemetry remains readable. This follow-up requires a Controller app and sampler update, not a new four-pixel firmware or RetroPie deployment.

- Reorganized Gameplay, Configuration, and component documentation; made Academy learning and per-player backup file locations explicit across guides and READMEs. Clarified both pairing PIN flows, native packet bytes 7–8, and Menu Guard's native-position limitation. Standardized Gun Smoke display text while retaining exact filenames, added wrapping for audit/benchmark tables, and refreshed Help assets and PDFs. The documentation-review batch was deployed as an uncommitted development build; the subsequent Networking and community-guide additions were also deployed without a commit or release.

- Simplified the tracker display name to **MediaPipe Hands** in the interface, diagnostics, command help, and documentation. The `legacy` identifier and tracking behavior are unchanged.

### Added

- Community guides for building the hardware, understanding native Power Glove emulation, and troubleshooting by symptom, available in Help and PDF editions.

- Hand-and-target website icons for browser tabs and saved home-screen shortcuts, included in Controller installations and upgrades.

- Setup now starts with four labelled status markers matching the Off-mode pixels, plus tracking, controller output, and saved console details. Shared background checks distinguish failed checks from unavailable results and keep physical network-link health independent of RetroPie connectivity. Pairing wording makes the Controller matrix PIN requirement explicit for both methods.

- Native Super Glove Ball test tools for three stationary holds and ten movements per direction, with sampled tracking losses, gaps, and neutral button counts.
- Opt-in, bounded Controller/receiver timing traces and a separately built diagnostic native core. Normal transport, native-state format, and responsiveness settings are unchanged. No diagnostic deployment is performed automatically.
- Local original-video indexing, reviewed onset/settling and coordinate analysis, frame-sampling uncertainty, and annotated screenshots. Retimed or incomplete evidence requires review; no physical latency improvement is claimed.

### Validation

- Diagnostic core compiled on macOS; finite-buffer/export and timestamp-analysis regressions passed. A synthetic 100 fps, ten-frame response measured 100 ms with a 90-110 ms sampling bracket.
- Actual-device instrumentation overhead, live gameplay, synchronized hand/screen recording, and accepted stationary-jitter baselines remain pending.

## [0.3.2-rc.6] - 2026-09-06

Changes since rc.5. This candidate adds saved player setups, complete hand backups, signed controller sessions, and Setup/mobile refinements. Update both computers together: the default version-2 sender and receiver do not interoperate with older controller transport. The project base version remains 0.3.2; the release tag and installer manifests identify the candidate.

### Added

- Up to twelve Controller-stored players with individual sensitivity, Academy progress, Glove Master awards, and saved calibration. Switching players pauses output and requires fresh centering or explicit same-position reuse.
- Complete version-2 hand-setup backups with name, personal and effective sensitivity, software identity, and per-player calibration. Restore reviews complete sensitivity and calibration reuse separately, preserves Academy progress, and recovers safely after interrupted writes. Earlier version-2 backups work; portable version-1 exports are rejected. Internal stores migrate to version 4 with private recovery backups.
- Version-2 HMAC-SHA256 controller messages with receiver-issued challenges, replay/retired-session rejection, bounded nonblocking handshakes, and restart recovery. No input state is queued during negotiation, and the shared secret is absent from signed packets.
- Idle matrix controls for On, Dim, or Off with faint app, console-service, authenticated-console, and independent Wi-Fi pixels. Setup reports unavailable Wi-Fi telemetry separately from disconnection. The unprivileged host sampler is installed on setup/upgrade; the fourth pixel requires the matching matrix firmware. Game, T/L, startup, error, and pairing displays are unchanged.
- Exact software commit/candidate metadata and running matrix firmware readback. Older firmware reports unavailable identity instead of an assumed match.

### Changed

- Reorganized Setup wording and connection, pairing, attract, and power sections. One-time-code pairing is prominent; SSH password pairing remains available. Address checks distinguish name resolution from game delivery.
- Refined phone/tablet navigation, forms, and Academy/Play layouts down to 320 pixels.
- Moved hostname refresh off the controller send path without queues or new smoothing. Hardware microbenchmarks document packet processing cost separately from end-to-end latency.
- Extracted the shared page shell, Dashboard, Academy, Games, and tuning into maintained modules and removed obsolete UI definitions. Rendered pages remain byte-for-byte equivalent.
- Receiver defaults to signed input. The explicit temporary `--allow-legacy-controller` upgrade option closes after the first signed state and should be removed after migration.
- Updated README, Help, installation material, screenshots, architecture diagrams, PDF editions, and the maintained review parking lot.

### Fixed

- Preserved the contacted Linux address/interface for UDP handshake replies when RetroPie has Ethernet and Wi-Fi on the same subnet. Replies require HMAC, fresh request/session identifiers, and the configured receiver port.
- Setup retries failed loads/actions, retains unsaved connection edits during refresh, and clears pairing approval after destination changes. Device-setting writes are serialized, private, and atomic; pairing-key changes disarm output.
- Start/Stop worker requests report pending delivery and retry only the latest intent. Supervised workers read pairing credentials from private configuration rather than process arguments.
- Receiver timeouts release native input and the virtual gamepad; rejected traffic and handshakes cannot postpone release. Malformed nested profile messages no longer terminate the listener.
- Glove Master replaces the final lesson panel after all sixteen lessons, avoiding an extra panel pushing the page downward. Start again restores the lesson panel.

### Validation and remaining work

- All 355 tests pass on Python 3.7 and 3.12. Source/documentation audits, package verification, browser checks, and visual PDF inspection pass.
- Both devices ran the completed code at `a7131f8`. Cross-device dry-run tests accepted both fresh sessions, dropped negotiation frames, and rejected retired-session input. Production handshakes worked through both RetroPie addresses. Controller firmware matched, Wi-Fi status was connected, and saved hand settings, calibration, pairing, and Start/Stop choice were preserved.
- Full live gameplay, synchronized camera-to-display latency, stationary jitter, and fresh-device installation checks remain release gates. Earlier successful native Super Glove Ball gameplay does not substitute for repeating gameplay on this candidate. This is not the final 0.3.2 release.

## [0.3.2-rc.5] - 2026-09-06

Cumulative release-candidate notes since 0.3.1. This candidate adds the refined
idle matrix animation, reproducible live latency baselines, and updated native
gameplay validation. Visible camera-to-game latency and a reliable stationary
jitter baseline still need a coordinated video test; this is not the final
0.3.2 release. The project base version remains 0.3.2, with the candidate identity
recorded by the release tag and installer manifests.

### Added

- Added `scripts/measure-vision-status.py` for read-only, bounded latency baselines.
  It ignores duplicate cached status samples, separates changing run conditions,
  and reports observed timing distributions and optional neutral X/Y variation.
  Reports contain aggregate measurements, with explicit limits for unmeasured
  network, receiver, core, and display stages. Recognition and movement defaults
  are unchanged.
- Recorded separate live movement, requested-stationary, network round-trip,
  and native-publication cadence observations. The movement window retained
  detection in all 315 observed samples and measured 132.8 ms read-to-send p95;
  physical display latency and a reliable stationary-jitter baseline remain
  separate validation steps.
- Added a camera-controlled Rock Paper Scissors page at `/play`. A closed hand
  plays rock, an open palm plays paper, and the held V-sign plays scissors in a
  first-to-three match against Pixel Pal. It reuses the local practice-camera
  lease, pauses cabinet input while open, and provides touch and mouse controls.
  Help now points readers to its illustrated Gameplay Guide section, while This
  cabinet retains a direct link to the game.
- Confirmed every implemented native Super Glove Ball action during a completed
  live game: open-hand release/throw, fist grab/catch, index-point Robo-Bullet,
  and fist-plus-forward Power Punch, alongside Start and continuous X/Y. Movement
  is playable and substantially improved; residual latency remains the next
  refinement target. Unused wrist-rotation and packet-button fields stay neutral.

### Changed

- Refined the idle matrix animation with a double-flash lightning bolt, separated
  fingers and thumb, a consistent cuff buckle, a longer fist hold, and a smaller
  travelling spark. Grayscale shading and a gradual glow finish the four-second
  loop. Added a preview rendered from the sketch's actual frames; physical LED
  appearance remains a separate check. Requires a matrix firmware update.
- Updated native compatibility test assertions to match the already documented
  completed-game confirmation and deliberately neutral unused packet fields.
- Corrected relay-test mock argument access for Python 3.7 compatibility.
- Adopted **VirtualGlove Controller** as the user-facing name for the
  Arduino UNO Q device throughout current guides, while retaining literal
  `uno-q` commands, filenames, host placeholders, and hardware-specific notes.

- Remembered the player's explicit Start/Stop controller choice across UNO Q
  application and system restarts. Registered RetroPie launches now maintain a
  renewable session only while RetroArch is running, allowing an armed controller
  to reconnect after an application restart without emitting into EmulationStation
  or the runcommand menu. Stop remains sticky; game exit, unknown games, and stale
  sessions release controls. Dashboard now distinguishes armed delivery from the
  live game session.
- Standardized numbered and bulleted lists across the Markdown guides. Built-in
  Help now keeps wrapped and loosely spaced items together, and generated PDFs
  keep every marker beside its complete item at page boundaries.
- Connected Super Glove Ball's native open hand, closed hand/fist, index-point,
  and calibrated signed-Z packet fields. The UNO Q publishes five-finger compound
  recognition explicitly; the custom Nestopia core emits `$00`, `$FF`, `$0F`,
  and absolute depth for throw, grab, Robo-Bullet, and fist-plus-forward Power
  Punch validation. Exact-ROM headless traces verify the ten-byte packet values;
  wrist rotation and remaining native button codes stay neutral.
- Replaced Glove Academy's threshold-first Tune panel with a Pixel Pal-guided
  personalization wizard. Families choose the problem, confirm clear framing,
  record gesture-specific steps, pass a two-use preview test, and then save only
  affected shared components. Raw numerical controls now live under Advanced.
- Added dedicated **Show your hand** and **Find neutral** artwork, clearer Start
  and Select lesson titles, and an intentional **Set this as my center** action.
- Added an optional local Academy diagnostic. It exercises the deployed proven
  tracker, emits an aggregate report without images or landmarks, and deletes
  its temporary video after analysis, cancellation, or a 30-minute abandonment.
- Added advisory hand-framing, darkness, and backlighting guidance without
  changing camera exposure automatically.
- Reduced the deliberate V-sign Start hold from 650 ms to 500 ms while
  retaining its short pulse, interruption cancellation, Menu Guard priority,
  and 300 ms visible-release rearm guard. Select remains a 150 ms hold.
- Evaluate directions, finger curls, wrist rolls, and Closed Hand on every fresh
  inference result. Glove Zap and Pull Back now reject stationary near/far hands
  and one-frame scale jumps by requiring two beyond-threshold observations plus
  0.10 normalized palm-scale motion in the intended direction within 250 ms.
  Existing held, pulsed, turbo, and toggle mappings remain unchanged.
- Added rolling camera-read-to-send and changed-control-to-send p50/p95 readings
  to Dashboard, including continuous native X/Y changes. The native coordinate
  benchmark now verifies a deliberate step reaches 90% within 150 ms without
  adding another queue or core-side smoothing.
- Added local-only fixed and user-paced camera record/replay tools for identical-frame comparisons of
  MediaPipe Hands thread counts, experimental Tasks Video, 640×480 versus
  full-field 512×384, and preview-open versus preview-closed cost. The recorder
  covers near/far, gesture, jitter, depth, and recovery cues. Guided capture
  keeps a live browser preview visible, records each step only after player
  confirmation, and releases the camera when complete. Clips are temporary and
  never used for training.
- On the deployed UNO Q, preliminary 300-sample steady-state windows kept the
  640×480 camera-read-to-decision p95 at 127.9 ms with Dashboard closed and
  125.7 ms with its stream open. A 16-lane guided replay retained MediaPipe
  Hands at 640×480 with four threads: Tasks Video roughly doubled inference
  latency, and 512×384 did not meet the required 15% improvement while producing
  more false activations. Controller-enabled game measurements remain a
  separate acceptance step.
- Promoted the Project Overview PDF to the first position in built-in Help's
  Technical Documentation section and reordered that section from broad system
  orientation through increasingly specialized implementation material.
- Made the deployed legacy-lite MediaPipe tracker explicit while retaining an
  opt-in Tasks Video path for controlled comparisons. Camera capture now drains
  continuously into a newest-frame slot, background JPEG work can drop stale
  previews, and live diagnostics report frame freshness, inference cadence,
  skipped captures, and preview cost.
- Named the tracker choices **MediaPipe Hands** and **MediaPipe Tasks
  Video (experimental)** in Dashboard and documentation while retaining the
  stable `legacy` and `tasks-video` command identifiers.
- Replaced Glove Academy's mislabeled single-finger curl in the **Close your
  hand** lesson with a dedicated closed-fist illustration. The intentionally
  six-digit glove remains part of Pixel Pal's Extra-Digit Hunt, and the pose is
  now shown in the Gameplay Guide, Configuration Reference, quick reference,
  and Programs A-I manual wherever closed-hand recognition is taught.
- Made **Skip lesson**, **Previous**, and automatic lesson completion mutually
  consistent. Manual navigation now invalidates older recognition responses and
  pending automatic advances, so one button press changes the lesson once.
- Added guarded UNO Q recovery for one UVC camera. Installation may run without
  a camera; the first healthy sighting records the camera and its real parent hub
  in a root-owned allowlist, and a later healthy sighting updates the association
  if the camera moves. After a sustained outage the helper validates and resets
  only the last observed hub. Recovery is rate-limited, never loops during one
  outage, and leaves ordinary camera reopen attempts as the first response.

## [0.3.1] - 2026-09-05

Documentation and Help maintenance release adding Pixel Pal's deliberately
spoiler-free guide game and keeping packaged documentation verifiable.

### Added

- Added Pixel Pal's Extra-Digit Hunt to the two illustrated gameplay guides.
  Readers count every preserved six-digit glove once per appearance, then find
  the verified per-guide answer at the back. Built-in Help keeps the answer
  behind an explicit reveal, accessible descriptions identify qualifying art,
  and a checked manifest prevents future artwork changes from making the answer
  stale. The App Lab package builder now refreshes its tracked checksum companion
  after each successful build so guide updates cannot leave a stale digest.

## [0.3.0] - 2026-09-05

Stable feature release covering shared recognition, native Super Glove Ball
support, simplified personal tuning, repeatable two-machine installation, and
the completed illustrated documentation set.

### Native Super Glove Ball and emulator support

- Confirmed the exact Super Glove Ball ROM's ten-byte native packet, MSB-first
  reads, `$A0`/`$5F` detection, `$3F` terminator, native `$82` Start, and
  continuous X/Y behavior in a deterministic headless trace.
- Corrected the custom Nestopia core to wrap the exact ROM's stream at ten
  bytes, center zero precisely, and neutralize stale, lost, uncalibrated, and
  wrong-profile samples instead of retaining a prior coordinate.
- Added reversible per-ROM native Nestopia/FCEUmm selection plus a RetroPie-only
  isolated core installer; stock Nestopia remains untouched.
- Audited all eight listed US ROMs: only Super Glove Ball consumes native
  multi-byte glove packets; the other games use standard controller-bit
  mappings through FCEUmm.
- Added a reproducible matched-savestate direction benchmark. Native Super
  Glove Ball visibly activates and releases every axis by frame 3, including a
  3.1% X step; FCEUmm Gun Smoke polls input on frame 1 and visibly activates
  and releases every direction by frame 2.
- Compared the exact Super Glove Ball ROM in both cores, confirmed that FCEUmm
  remains standard-joypad-only, and corrected native Y wrapping so its packet
  and screen position span bottom, center, and top.
- Added an optional RetroPie installer offer that builds the pinned GPLv2
  native core locally, registers both per-ROM launch choices without changing
  the saved FCEUmm selection, and installs the upstream license beside the core.

### Installation and distribution

- Added versioned UNO Q and RetroPie installers with verified downloads, repeatable updates, backups, and read-only checks.
- Included the early-start and shutdown helpers in UNO Q installation; App Lab's command-line tools install the app and Arduino sketch.
- Added optional emulator installation and registered-game checks, including Bad Street Brawler's game-specific Glove Zap setting.
- Simplified installation instructions and moved manual repair and packaging details into the technical reference.
- Added release packaging and automated installer tests after fresh-device and
  physical gameplay validation on the UNO Q and RetroPie console.
- Added installation manifests shared by both package installers and Wi-Fi
  deployment. Updates back up and remove unchanged obsolete application files,
  preserve local edits, and provide interrupted-update recovery and read-only
  inventory checks.
- Allowed UNO Q deployments to select an explicit SSH identity and expanded
  the live deployment gate to verify every published technical guide and PDF.
- Made `config/profiles.json` release-owned and replaceable during updates so
  the shared recognition defaults supersede legacy per-game thresholds; the
  previous file is backed up and personal calibration and tuning under `data/`
  remain preserved.
- Hardened release validation so installer packages must contain the shared
  profile baseline and current recognition, tracking, tuning, and native-core
  selection modules. Update tests explicitly preserve neutral calibration and
  personal gesture tuning while replacing release-owned defaults.
- Preserved existing profile configuration during installation and Wi-Fi updates.
- Unified release/deployment payload selection and installer templates; removed
  unused helpers and state.

### Recognition, performance, and safety

- Made explicit and automatic neutral calibration accept only complete hand
  observations at 70% confidence or better. Documented its 24-frame averaging,
  circular wrist mean, 95th-percentile jitter measurement, repeatability limits,
  atomic replacement, and separation from portable recognition defaults.
- Removed avoidable gameplay diagnostics: finger geometry is measured once,
  detailed landmarks are prepared only at the 5 fps preview cadence, and idle
  tuning skips measurement work while unchanged configurations are reused.
- Made Menu Guard and the V-sign mutually exclusive with a clear pinky deadband.
  Menu Guard now has priority, cancels pending Start pulses, and suppresses every
  ordinary controller button while the safety pose is active.
- Made recognition settings global across game mappings, reduced movement travel
  with `0.28` activation and `0.14` release baselines, and recorded neutral X/Y
  jitter so only noisy setups automatically receive higher safe thresholds.
- Expanded Glove Academy from twelve to sixteen mapping-independent lessons with
  roll left/right, close hand, and a shared menu-guard pose. Practice polls every
  75 ms and controller delivery remains paused.
- Hardened the V-sign Start command after live Gun Smoke/FCEUmm testing exposed
  accidental pause pulses. Start now requires a stable 0.65-second hold and a
  continuous 0.30-second non-V release before it can rearm; movement, A/B, and
  Select timing are unchanged.
- Reduced Start and Select pose debounce to 0.15 seconds before the later
  live-tested Start-specific hold and rearm protection, retaining one press per
  pose and release before repeating.
- Fixed controller session resets, malformed packet rejection, and timeout
  release during rejected network traffic.
- Applied finger release thresholds consistently in Programs E, F, and G.
- Matched tuning feedback to each recording step and made failed matrix
  commands retry.

### Documentation and licensing

- Expanded the third-party runtime inventory for the modified Nestopia core
  with its patch checksum, affected files, runtime/install boundaries, GPL
  preservation rules, and pinned-update procedure. Documented stock RetroArch
  and FCEUmm as externally installed RetroPie dependencies and added an audit
  check that prevents the Nestopia revision or patch digest from drifting away
  from the published notices.
- Preserved Nestopia's original source copyright and GPL header verbatim,
  added a separate file-by-file VirtualGlove modification ledger, made
  the native-core build reject header changes, and installed that ledger beside
  the optional core and its upstream `COPYING` file.
- Centered gesture, profile, and matrix artwork in Help and printable table
  columns. Grouped related startup and attention-state matrix photographs into
  compact visual rows where side-by-side comparison is clearer.
- Added a dedicated menu-guard illustration and substantially enlarged the A/D/H
  experiment artwork in built-in Help and the gameplay PDF, with balanced text columns.
- Added the isolated `lr-nestopia-powerglove` research patch, reproducible pinned
  build, tracing, and guarded latest-sample bridge. Exact-ROM validation is now
  recorded alongside the retained FCEUmm fallback.

### Added

- Added an optional permanent UNO Q early-start helper after a successful physical cold-boot trial. It releases the installed sketch earlier on each boot while preserving the system boot display and existing hourglass animation.
- Added a Matrix display guide in Help and PDF form, covering every display state, profile letters, pairing sequences, troubleshooting, and photographs of the physical display.
- Added a pulsing startup hourglass before Router Bridge initialization. A dedicated Arduino sketch display task keeps it moving while Linux is starting; ordinary app status then selects the glove, profile, or Academy display. The protected system boot display remains unchanged.
- Renamed the Learn section to Glove Academy in navigation, the page heading, and current guides. Kept `/learn` links, lesson/tuning behaviour, and L/T matrix indicators unchanged.
- Added startup stage timings for library imports, model preparation, camera initialization, and first inference.
- Added individual gesture illustrations and Pixel Pal to the website and friendly manuals, with a smaller PNG for web use.
- Preserved and bundled the unmodified Google Hand Landmarker model with Apache 2.0 license text, provenance, and checksum.
- Added offline model-cache installation and recovery from the bundled copy, with verified download fallback only when the bundle is absent.
- Made package builds verify the model and required license files before reporting success.

### Changed

- Preloaded OpenCV and MediaPipe in the background when the vision worker starts, keeping controls responsive and the camera off until requested. On the tested cabinet, first activation after a reboot took 1.21 seconds once preloading completed.
- Made `/dashboard` the default page, retaining redirects from `/` and `/debug`.
- Made web footers use the release version, with a development indicator on dev builds.

### Gesture tuning simplification

- Replaced seven recordings with open hand, gesture, open hand (three seconds each).
- Added optional all-finger hand setup using a gentle fist with the thumb outside.
- Added live extended/curled finger feedback sharing V-sign and thumbs-up recognition checks. Existing saved thresholds remain compatible.
- Completed live camera validation on the installed UNO Q system.
- Featured common tuning controls and grouped directions, wrist rolls, and other combinations under More adjustments. Added explicit movement-specific starting-position and return instructions for Glove Zap, pull-back, directions, and wrist rolls.
- Added pull-back as the twelfth ordinary Learn lesson, with a live action indicator, backward-distance feedback, and personal pull thresholds.
- Gameplay movement mappings now use shared activation/release states for wrist controls, forward push, pull-back, movement answers, and braking. Preserved game button mappings, pulses, and pull-toggle edges; clear depth activation on tracking loss.
- Matched Tune’s T animation to Learn’s L using the same scan line, trailing glow, brightness, and frame timing.
- Standardized Glove Zap and Pull Back labels across Learn, Tune, and the guides.

### Documentation and firmware reconciliation

- Documented optional five-finger hand setup, three recordings of three seconds, preview/save/discard/reset, extended-only finger handling, and unchanged version-1 saved settings.
- Updated ordinary Learn to twelve lessons with Glove Zap and Pull Back, and documented shared gameplay activation/release states while retaining profile mappings and menu holds.
- Documented matching scanning L/T animations and consistent action names.
- Recorded the verified Zephyr 1.0.0 platform and pinned sketch libraries, distinguishing platform installation, compile-only validation, and firmware upload.
- Refreshed maintained guides and their PDF editions. Historical entries above retain the behaviour and names at the time of each change.
- Completed live camera, game-control, cold-boot, and physical display checks on the installed systems in addition to the automated release checks.

### Complete-pose validation before tuning suggestions

- Automatic analysis now requires all selected fingers to match together in at least 90% of accepted samples, including opening and final release phases.
- V-sign validates extended index/middle alongside curled ring/pinky; thumbs-up validates extended thumb alongside four curled fingers, using shared recognition checks and existing personal extension thresholds.
- Failed analysis identifies the finger/phase and clears the preview without modifying saved settings. Existing holds and orientation-flexible thumb extension remain unchanged.
- Added regressions for invalid extended fingers in each phase, personal thresholds, exact boundaries, noise tolerance, simultaneous pose failures, invalid samples, and saved-value preservation, then completed live camera validation.

### Bad Street Brawler Glove Zap

- Mapped forward-push activation to a 180 ms simultaneous Left + Right pulse in the Bad Street Brawler profile. Require release before retriggering; cancel on menu poses, tracking loss, and recalibration.
- Enabled opposing directions in Bad Street Brawler's FCEUmm game options while preserving global settings. The existing RetroPie receiver and gamepad mapping need no changes.
- Corrected the earlier documentation claim that this attack required native glove support. Added pulse, cancellation, rearming, and other-profile regressions; all 155 tests passed. A two-frame headless test confirmed the game-specific options load. Live attack validation remains outstanding.


### Repeatable RetroPie Glove Zap configuration

- Added `powerglove-bsb-zap` with read-only checks and explicit `--apply` setup.
- Checks installed FCEUmm/RetroArch and game emulator selection; reports missing dependencies or incompatible selection without silently changing either.
- Preserves inherited options and global settings; backs up and atomically updates the game file, with repeat-run detection and rollback instructions.
- Added six isolated tests for creation, preservation, inheritance, missing cores, wrong emulator selection, read-only mode, running games, redirects, and symlinks.
- Documented installation, use, limitations, and the remaining live gameplay check.

## [0.2.5] - 2026-09-04

This release adds web game mappings, personal gesture tuning, reliable game-launch
profile selection, and refreshed illustrated manuals.

### Added

- Added a dedicated T on the UNO Q matrix while gesture tuning is active.
- Added a Games JSON editor with paired RetroPie access, duplicate-name validation, conflict detection, verified saves, backup download, and restoration.
- Added guided Learn tuning with camera measurements, independent gesture thresholds, temporary previews, and persistent personal adjustments shared across profiles.
- Added a confined RetroPie Games service on TCP 55358 and included it in installation and health checks.

### Fixed

- Moved game mapping editing into Setup and compacted Learn tuning, placing threshold values beneath the camera.
- Published UDP profile control through a persistent App Lab brick, acknowledged queued requests independently of camera startup, and corrected launch-hook rejection reporting and configuration-error handling.
- Kept profile changes responsive during blocked camera startup or reads, and reused the camera and tracker when switching between active profiles.
- Added exact compressed ROM filenames to the default registry so supported `.zip` and `.7z` games can select their profiles.

### Documentation

- Refreshed all six interface screenshots on September 4, 2026, blurring camera imagery before capture.
- Illustrated Setup's Games section and Learn's compact Tune layout across the guides, including the T matrix indicator.
- Regenerated the printable manuals to match the updated Markdown and screenshots.
- Reorganized the overview and installation guide around a complete, numbered setup path: Git download, App Lab package import, UNO Q host setup, RetroPie installation, pairing, and gameplay checks.
- Added Programs A–I controls to the overview and a complete command-line reference with project flags, defaults, arguments, and the system-command options used in the guides.
- Applied reader-focused writing conventions across the guides, added first-round game exercises, and corrected the RetroPie update path. PDF regeneration remains a separate publication step.
- Reviewed all Markdown guides for natural English, replacing sentence fragments and compressed notes with complete explanations while retaining concise tables and release entries.
- Revised the Quick Reference with complete installation prerequisites, camera inspection commands, embedded screenshots, calibration explanations, and step-by-step game registration. Clarified shutdown readiness and local tests.
- Corrected stale lesson counts, profile descriptions, calibration behaviour, pairing guidance, reboot verification status, and receiver removal steps.
- Proofread the Quick Reference and normalized Markdown list indentation and continuation text for consistent rendering.
- Regenerated all ten PDF editions, repaired internal section links, and improved heading and image pagination.

## [0.2.0] - 2026-09-03

### Added

- Added an app-owned Avahi resolver brick that survives App Lab Compose regeneration, replacing the temporary direct socket mount.
- Added one-command host setup for RetroPie and UNO Q, with managed-file backups, preserved private configuration, delayed startup, and read-only PASS/FAIL/ACTION checks. Empty pairing tokens no longer cause restart loops.
- Added explicit A, B, and GLOVE ZAP practice lessons and live indicators. Learn consistently uses the general profile without changing the selected game.
- Added a Glove Master completion achievement to Learn after all eleven lessons are recognized, with Start again and Dashboard actions. Skips do not count.
- Added hand illustrations to every Learn lesson and finger/pose feedback for Start and Select. Learn accepts confirmed menu poses after their short button pulse ends, rather than requiring a second hold longer than the pulse.
- Added a live active-profile selector to the Dashboard without changing the startup profile saved on Setup.
- Added temporary Learn sessions that start vision while preserving the selected profile and desired controller state, including multi-tab leases and automatic recovery when a page disappears unexpectedly.
- Added a dedicated matrix gestures-idle state with a pinball-style animated glove, separate from both true shutdown and the flashing error X.
- Added a dedicated Learn-mode matrix state with a bright `L` and moving grayscale scan highlight.
- Added a root-owned tmpfiles rule that restores shutdown-helper readiness after reboot or App Lab application replacement.

### Changed

- Shutdown now requests a graceful system halt instead of poweroff, which was observed to reboot the UNO Q. Reinstall the host helper to apply this change; hardware tests subsequently confirmed automatic restart with both the powered hub and direct Mac USB connection. Remaining halted is a known unresolved limitation.
- New installations leave the RetroPie destination blank, show generic hostname examples, and keep local practice available before pairing. Controller start requires a destination; saved destinations survive updates.


- Added persistent host Avahi resolution for `.local` gameplay and pairing destinations, with five-second address refresh and deployment mount setup.
- Standardized Dashboard/Learn Calibrate actions with red busy and blue completed feedback, consistent navigation buttons, and shorter Connection/Shutdown labels.
- Prioritized controller transmission before matrix updates and limited browser JPEG encoding to 15 fps; added inference_ms and send_ms diagnostics.
- Prepared SSH pairing dependencies separately in the persistent runtime cache so dependency downloads do not consume the SSH connection deadline.
- Tuned thumbs-up/Select closed-finger detection to 0.42 using live pose measurements, retaining the straight-thumb requirement and deliberate hold.
- Tuned V/Start closed ring and pinky detection to 0.42 using live pose measurements, retaining straight index/middle checks and the deliberate hold.
- Tuned curl activation/release to 0.50/0.35 using live comfortable index-curl measurements. Learn now follows the same hysteresis state as gameplay, independent of pulsed buttons. Calibration resets held finger switches.
- Finger curl now uses the strongest joint bend and includes the base knuckle for the four fingers. Learn exposes exact curls, a magnified landmark view, and forward-movement readings. Push lessons use continuous feedback so a one-frame event cannot be missed by browser polling.
- Camera finger curl now uses 3D world landmarks, with an aspect-corrected normalized-depth fallback. Movement and gesture thresholds are unchanged.
- Made Dashboard and Learn show camera/tracker startup with elapsed time and a first-start explanation, without enabling the camera in Gestures off.
- Kept Learn startup feedback updating before camera frames arrive and disabled centring until vision is active.
- Replaced generic Program A–I labels on Dashboard and Setup with the program letter and its intended game or use, while retaining the existing profile IDs.
- Standardized the reader-facing game name “Gun Smoke” throughout Help and the public guides; exact `Gun.Smoke` ROM basenames remain unchanged for matching.
- Made leaving Learn restore the selected profile, camera state, and controller state. Loading or refreshing the Dashboard now clears abandoned Learn sessions, prevents their old heartbeats from reactivating vision, and reapplies the selected mode.
- Made Wi-Fi deployments preserve VirtualGlove as the UNO Q default startup app so the dashboard returns after a board reboot.
- Made Wi-Fi deployments restore the shutdown readiness marker when the installed host watcher is active.
- Extended deployment health verification to tolerate a three-minute cold App Lab runtime startup.
- Made deployment verification use the UNO Q address from the active SSH connection instead of accidentally selecting a Docker bridge interface.
- Made **Gestures off** a healthy worker state that releases controller input, closes the camera and MediaPipe tracker, and keeps the website and authenticated RetroPie profile listener available.
- Made camera and model initialization lazy so idle mode performs no capture or vision processing and can return to an active profile without restarting the website.
- Reworked the matrix attract sequence into distinct pinball-style beats: a four-frame energy sweep, a broad travelling cuff, a staged glove reveal, intermediate finger curls, an eight-position spark with a comet trail, one outline pulse, and a readable hold.
- Used the UNO Q matrix's full eight-level grayscale range to separate the dim glove body, spark halo, bright spark, and whole-glove pulse.

### Documentation

- Documented the UNO Q matrix as an eight-level monochrome DMD/BitPixel-style design target, including silhouette, contrast, motion, pulse, and physical review guidance for future animations.
- Standardized source headers with each file's purpose, author, copyright, SPDX license identifier, local history, and links to the complete history.
- Documented public interfaces and non-obvious security, lifecycle, tracking, packaging, and rendering functions.
- Added this centralized project changelog and its print-ready PDF edition.
- Added an automated audit for required source headers, module descriptions, and production Python interface docstrings.
- Added a complete configuration reference covering JSON templates and active copies, gesture thresholds, manifests, RetroArch mapping, systemd units, generated state, secret handling, and the App Lab installation ZIP location.
- Added GitHub Actions checks for supported Python versions, tests, source and documentation audits, syntax, PDF builds, and App Lab installation ZIP verification.
- Added a security policy for private reporting, pairing and network boundaries, shared-token handling, shutdown permissions, and dependency integrity.
- Added a contributing guide for code style, tests, documentation, changelog, generated artifacts, commits, and pull requests.
- Added reusable documentation and App Lab installation package verification tools.
- Added an illustrated, one-page-per-game handbook for all eight automatically configured titles, with original direction, finger-pose, wrist, and depth art.
- Placed cropped gesture illustrations beside the corresponding instructions in the gameplay handbook, including the universal V-sign and thumbs-up controls.
- Added the same contextual gesture illustrations to every Program A-I card and documented the menu gestures shared by all nine programs.
- Added an off-script gameplay section that encourages safe experiments with other NES and Famicom games, especially the unassigned A, D, and H programs.
- Updated the cabinet cheat sheet with off-script profile testing, safe behaviour for unknown games, and exact ROM registration guidance.
- Renamed the built-in installation Help route, retained the original URL as an alias, and aligned its summaries with the Play Checklist terminology.
- Extended the documentation audit to require Help-library coverage and a gameplay section for every title in the shipped game registry.
- Expanded Wi-Fi deployment verification to confirm the current installation and gameplay guides, raw Markdown, and gesture artwork on the UNO Q.
- Fixed the Help renderer so the allowlisted gesture images embedded in control tables appear alongside their actions, while unsafe raw HTML remains escaped.
- Extended UNO Q deployment checks across every Help guide and representative gameplay and Programs A-I illustrations.
- Documented the required Markdown-to-PDF workflow and UNO Q Help synchronization steps for documentation contributions.
- Added offline PDF links to every public Help guide and the project overview, while keeping the cabinet-specific quick-reference PDF private.
- Included the nine allowlisted public PDFs in UNO Q deployments and App Lab installation packages, with package and live-route verification.
- Established `dev` as the integration branch, documented release and hotfix promotion into `main`, and enabled CI validation for pushes to both branches.
- Refreshed the Dashboard, Learn, and Setup screenshots from the running UNO Q after the tagline, compact diagnostics, and safe-shutdown controls were added.
- Added an offline Help library that renders the maintained public Markdown guides with responsive navigation, contents links, illustrations, tables, code samples, and access to the original source.
- Added a dynamic **This cabinet** Help page whose UNO Q links follow the browser's validated hostname or IP and whose non-secret RetroPie values come from the active configuration.
- Rewrote the configuration reference for public installations, with guided UNO Q and RetroPie setup, field-level behaviour, safe gesture tuning, network boundaries, backup and recovery advice, and symptom-based troubleshooting.
- Renamed the Field Guide as the Installation Guide and generalized camera instructions for UVC-compatible USB cameras while recording the Razer Kiyo as tested reference hardware.

### Fixed

- Changed Wi-Fi deployment to use SFTP staging and terminal-backed remote commands for UNO Q systems that stall non-terminal SSH sessions.
- Allowed the UNO Q deployment health check to use the board's current IP when its `.local` name pauses during a container restart.
- Published the host shutdown request atomically so a filesystem observer cannot consume the request between file creation and the final content write.
- Updated the GitHub Actions workflow to use the current Node 24 action releases and run the Python 3.7 compatibility job on Ubuntu 22.04.
- Corrected Program I so index curl accelerates in Knight Rider, a forward push accelerates with turbo, and thumb curl fires the weapons.

## 0.1.0 - 2026-09-03

### Added

- Camera-only Power Glove tracking on Arduino UNO Q with MediaPipe.
- Gesture profiles for Bad Street Brawler, Super Glove Ball, and cartridge-free Programs A-I.
- Authenticated UDP profile selection and virtual Linux gamepad output for RetroPie, including per-game runcommand hooks.
- Dashboard, live diagnostics, offline gesture lessons, configuration controls, camera recovery, controller start/stop controls, and UNO Q matrix feedback.
- Wi-Fi deployment, App Lab packaging, runtime-asset retrieval, branded PDF generation, and a fixed-purpose host shutdown helper.
- Project overview, installation guide, quick reference, profile handbook, third-party component notice, screenshots, and reproducible build instructions.

### Changed

- Delayed RetroPie receiver startup until EmulationStation finishes its initial device scan, preventing the virtual controller from disrupting cabinet input.
- Made the controller start disarmed and kept tracking/dashboard operation alive when RetroPie or the camera temporarily becomes unavailable.
- Moved private device settings and downloaded model data outside the App Lab installation ZIP.
- Changed the App Lab installation ZIP to download Google's Hand Landmarker model on first launch and verify its pinned SHA-256 digest before installation.

### Fixed

- Recovered cleanly from USB camera disconnects and slow UVC camera wake-up.
- Kept the vision loop responsive through receiver, DNS, Wi-Fi, and mDNS loss.
- Corrected password pairing so credentials never appear in command arguments and the shared token is transferred and installed reliably.
- Corrected UNO Q dependency isolation, secure token upload, PDF builder file mode, landscape diagnostics layout, and cabinet launch integration.

### Security

- Added short-lived TLS pairing with certificate comparison, a physical single-use PIN, bounded handshakes, and restricted token-file permissions.
- Required confirmation and a fixed host-side request path for system shutdown.
- Added a third-party component notice covering licenses, provenance, pinned versions, checksums, and update procedure.


### Neutral calibration retention

The app now saves completed calibration so the reference survives transitions
between Learn and gameplay, profile changes, camera reconnections, and restarts.
When you recalibrate, the app replaces the saved reference atomically.


### RetroPie mDNS installation

The RetroPie setup command now installs `avahi-daemon` and `libnss-mdns`, enables Avahi at boot, and checks both the service and dependency. Existing hostname configuration and pairing settings are preserved. Fresh-machine installation has not yet been tested.


The UNO Q installer also installs and checks `libnss-mdns` alongside Avahi for host-level resolution, while retaining the separate app-container resolver.


### Documentation and shutdown wording consistency

The documentation now explains when to recalibrate, which files to back up,
and what the hand-identification score means. Shutdown confirmations also
explain that the UNO Q may restart automatically.
