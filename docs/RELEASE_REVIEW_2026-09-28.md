# VirtualGlove release review — 28 September 2026

## Review boundary

This review covers the development checkout, including shared Router code and UNO Q packaging. It does not certify every published release, hardware architecture, or emulator. No release, deployment, or saved console configuration change is part of this review.

## Code and integration reviewed

- Identity-based session routing, enabled-system policy, physical reconnect behaviour, temporary RetroArch settings, configuration precedence, owned-profile repair, and installer-only migration.
- Shared app selection, authenticated session ownership, fail-closed leases, Matrix manifests and expiry, chooser assets, same-origin requests, service startup, and failed-upgrade recovery.
- Product installers, preserved pairing and registries, console transport, game/frame integration, and product-specific input boundaries.

The shared library and UNO runtime are synchronized from Controller Router into both products; product adapters retain their own pairing, game rules, and virtual source requirements.

## Corrections

The shared UNO installer now restores both old unit definitions and the product startup service after a failed upgrade, restores the old Matrix app if its staged replacement fails, and rejects missing service units before installation. Previously it restored software but left product startup stopped. The chooser returns an explicit unavailable response for missing assets and rejects malformed browser origins without terminating a request. System discovery skips malformed Batocera entries and unreadable RetroPie registrations instead of hiding later valid systems or failing the catalogue.

VirtualGlove’s stale Batocera regression expectation was updated: launch hooks report sessions and must not call the retired persistent config writer. The source review inventory is regenerated after the reviewed changes.

## Documentation reconciliation

The guides now distinguish console routing from UNO app ownership; separate shared Setup’s Players and Systems; describe NES-only defaults, preserved upgrade selections, native emulator exclusion, legacy udev routing, and native reservations; and explain core-override precedence and the narrow installer migration. Persistent RetroArch-writer descriptions were removed from current technical guidance. Dated optical and earlier release records remain historical evidence.

## Validation and release gates

VirtualGlove: 981 Python tests completed successfully, with three platform/environment skips. Shared bundle equality, Python syntax, and whitespace checks are also part of the review. Prior live evidence is preserved in Controller Router’s `docs/ROUTING_VALIDATION.md` and the product engineering reports. That evidence includes RetroArch 1.19.1, a separate 1.20.0 build, and 1.22.2; bounded game launches and configuration-preservation checks are distinct from physical gameplay endurance.

Before publishing a new candidate, validate the newly changed rollback path on a staged UNO Q installation, then repeat installation and upgrade checks using the candidate’s published artifacts. Physical wireless sleep/wake endurance and visible menu/exit checks remain release gates. A custom core or game override can intentionally replace Router session settings; inspect it when diagnostics and the actual selected player disagree.

All 32 generated manual PDFs were rendered for layout review (442 pages). Current downloadable guide copies are synchronized. Python and JavaScript syntax checks passed; shared Router bundles match exactly. A tracked-filename scan found no ROM or private-key files; VirtualGlove’s print-file ZIPs are enclosure assets. This was not an exhaustive repository security audit.

## Console installer recovery follow-up — 29 September

The former manual software-recovery limitation is corrected. Console installation now snapshots the managed payload, launch integrations, configuration and service state; restores them after installation or validation failure; and recovers an abrupt interruption on the next installer run. Recovery verifies snapshot contents and restored files, retains credentials and ownership, serializes installation, and detaches only Router’s owned Batocera generator overlay. Previously stopped services are not started by recovery. Operating-system package-manager operations remain outside the transaction.

Fifteen isolated recovery regressions cover RetroPie, Batocera and Recalbox layouts, entrypoint validation failure, successful installs awaiting pairing, interrupts, repeat recovery, corrupt backups, file permissions/ownership, links, and service activation. The complete VirtualGlove suite completed 995 tests successfully (three environment skips). Live failed-upgrade checks using candidate packages remain a release gate.


## Documentation review — 29 September 2026

Reviewed the maintained guide collections across VirtualGlove, R.O.B. Vision, and Controller Router by audience. Player Help now uses named controls, numbered tasks, expected results, and symptom-based recovery. Technical references retain platform diagnostics, configuration ownership, protocol boundaries, validation, and source links. Historical experiment reports remain engineering evidence rather than present-day setup instructions.

Checked player assignments, system selection, save/restore revision behaviour, input checks, launch routing, and app selection against Router's shared code and Setup controls. Checked Buddy's levels, gyro handling, gate assistance, Stack-Up clearance rules, and Test cues against its controller and dashboard. Checked VirtualGlove's game profiles, native hand-input boundary, camera checks, pairing, and Matrix instructions against its application and installer code. Documentation does not claim a new live gameplay validation from this editorial review.

Verification: all three guide collections have no unresolved local Markdown links or heading targets; VirtualGlove's documentation audit and four Help rendering tests pass. Rebuilt 33 maintained PDF editions, rendered all pages for visual inspection, and inspected key revised player pages at reading resolution. Preserved the separate engineering journey and technical test results.

Documentation standards cite Google developer documentation guidance, Microsoft procedure guidance, Diátaxis, and Xbox text/visual accessibility guidance. User instructions and technical contracts are reviewed separately to avoid exposing implementation details as player tasks.

## 0.6.0 candidate review — 29 September 2026

The next minor release target is 0.6.0. The stable installer links and release facts remain on the published 0.5.3 release until new candidate assets are built and accepted. The full local suite passes: 987 tests with three skips. The documentation audit passes for 25 maintained guides and the source audit passes for 298 tracked files. Shared Router files match both other projects; retired persistent RetroArch writers and the old UNO Q early-start service are removed. A tracked-filename check found no ROM, private-key, or credential files; this is not a complete security audit.

Before final release, build candidate packages from the reviewed commit, update release facts and generated website/manuals together, and test clean install, both product installation orders, upgrade and rollback on staged hardware. Check camera exposure, Matrix cues, game selection, Player 1 input, hotkeys, and physical-controller sleep/wake. Download candidate assets to verify checksums, Help, and PDFs. Earlier live tests apply to their recorded builds and do not certify the next candidate.

## RetroPie development deployment — 29 September 2026

The current development code was installed on retropie.local and retropieconsole.local with the bundled Controller Router, followed by current R.O.B. Vision source. Both consoles rebooted into EmulationStation with all three controller services active, zero service restarts, no boot error entries for those services, and executable shared pairing helpers. The NES `retroarch.cfg` checksums remained unchanged and both that file and `emulators.cfg` remained owned by `pi:pi`. Pairing files were present; game input was not exercised in this deployment check.

The first retropie.local install rolled back because its saved short UNO Q name, `arduiain`, did not resolve there. The same device's `arduiain.local` name resolved, so the saved destination was corrected before repeating the install. On retropieconsole.local, the previous recovery code attempted to copy 36 GB of RetroPie configuration, mostly untouched Skyscraper cache and downloaded game media. That pre-change attempt was interrupted and restored without changing software. Recovery now preserves those collections in place without copying them; the successful snapshot was about 627 MB. A regression test verifies that these directories survive rollback unchanged. Both successful installs reported zero technical failures and pending in-game control confirmation.
