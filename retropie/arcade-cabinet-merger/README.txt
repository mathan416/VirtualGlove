# VirtualGlove Arcade Cabinet Merger

This optional integration preserves the proven input arrangement used by the
VirtualGlove development cabinet. It is maintained with VirtualGlove, but it is
not installed by the standard RetroPie installer because its source devices and
button layout are specific to a two-player arcade panel.

The merger combines these Linux input sources:

- the two gamepad interfaces exposed by an Ultimarc I-PAC Ultimate I/O;
- up to two supported 8BitDo controllers; and
- the standard `VirtualGlove` gamepad for Player 1.

It publishes `Arcade Merged Player 1` and `Arcade Merged Player 2`. RetroArch
uses those outputs during gameplay, so the panel, handheld controller, and
VirtualGlove can participate without changing the standard VirtualGlove
receiver.

## Why this is optional

The ordinary RetroPie installation already works without this component. It
exposes VirtualGlove as a separate controller and leaves existing physical
controllers alone. The cabinet merger is for installations that deliberately
want several physical input sources to behave as the same RetroArch players.

The checked-in implementation is the exact source recovered from the working
development cabinet on September 19, 2026. Its device names and I-PAC raw
button numbers are therefore known-good for that cabinet, not universal
defaults for every arcade encoder or controller mode.

## Included files

| File | Purpose |
| --- | --- |
| `arcade-gamepad-merger` | Python/evdev merger used by the cabinet |
| `arcade-gamepad-merger.service` | Boot-persistent systemd service |
| `retroarch/Arcade Merged Player 1.cfg` | RetroArch autoconfiguration for Player 1 |
| `retroarch/Arcade Merged Player 2.cfg` | RetroArch autoconfiguration for Player 2 |
| `propose-controller-router.py` | Build but never apply the cabinet Router proposal |
| `cabinet-controller-router-migration.py` | Receipt-gated check, opt-in migration, and one-command rollback |

## Current behavior

- Buttons remain held while any contributing source holds them.
- Disconnecting a source releases only that source's state.
- Devices are rediscovered after hot-plug and are not identified by a saved
  `/dev/input/eventN` path.
- The most recently changed non-neutral source supplies each analogue axis.
- VirtualGlove Select is NES Select only. It cannot emit the dedicated merged
  hotkey-enable button.
- VirtualGlove contributes to Player 1 only; the I-PAC and 8BitDo controllers
  can contribute to both players.

## Reuse and future platform support

Treat the files here as a maintained reference integration, not as a blind
copy-and-install recipe. A similar cabinet must first confirm its exact Linux
device names, I-PAC interfaces, raw button codes, RetroArch mappings, and
hotkey policy.

Controller Router is now the generalized path for RetroPie, Recalbox, and
Batocera. `propose-controller-router.py` imports the development cabinet's known
I-PAC and 8BitDo ordering into a version-2 proposal, assigns VirtualGlove to
Player 1, and deliberately changes nothing. Review the proposal and run Router's
live preflight before accepting migration. The preflight requires one observed
control from every proposed physical source and creates each temporary merged
output without touching the installed Router configuration or RetroArch.

Keep this service and its RetroArch files installed but disabled after
migration. `cabinet-controller-router-migration.py rollback` restores the
previous Router file, FCEUmm override, receiver route, and exact enabled/running
state of the old merger in one command. The archived service remains the
cabinet's implementation reference until reboot, hot-plug, and gameplay
acceptance have passed.
