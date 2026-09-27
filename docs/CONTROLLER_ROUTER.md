# Controller Router

## Choose a controller app on the UNO Q

Start a game registered with VirtualGlove on the paired console and Controller Router selects VirtualGlove automatically. Gyromite and Stack-Up select R.O.B. Vision when that app is installed and paired. You do not need to open a website to play. Both services and websites remain online, but only the game's app controls input and the UNO Q Matrix. Router returns to its neutral animation when the game ends.

Open your UNO Q's `.local` address or LAN IP address without a port to view or manually select an app. When only VirtualGlove is installed, that address opens it. When both apps are installed, it shows a chooser. Finish any live game before changing apps manually. A direct top-level visit to either product's browser port selects it when no game is active. Use **Choose controller** in either app to return to the chooser.

Controller Router owns the UNO Q Matrix firmware. After reboot no app is selected and Router shows a neutral animation until a registered game reports its session. The selected app can request its own status, game, or temporary pairing animation. Its game input stops if Router's short lease expires. Pairing and manual controller changes are blocked during a live game. Existing console assignments, pairing, and game registries remain in place during upgrades.

VirtualGlove's browser is on port **8100**; its secure Setup service remains on **8443**. This UNO Q app chooser is separate from the console player assignments described below.

Controller Router gives physical gamepads and VirtualGlove clear player assignments in RetroArch. It creates up to four merged gamepads, named **VirtualGlove Merged Player 1–4**. Each merged player can receive one or more physical controllers; one chosen player can also receive VirtualGlove gestures in supported NES games.

The original physical controllers still navigate EmulationStation. During a Libretro game, Router sends their input through the assigned merged player so one button press is not interpreted twice. The merged devices are deliberately neutral in EmulationStation. Controller Router does not manage standalone emulators outside Libretro.

## Where Router is used

| Platform | What to expect |
| --- | --- |
| RetroPie | A standard VirtualGlove installation keeps its separate gamepad. Controller Router is optional unless another installed project has enabled the shared Router. |
| Recalbox and Batocera | Controller Router is the normal route for physical gamepads and supported VirtualGlove input. Existing Player 1 selection is carried into the Router configuration. |
| LaunchBox | Uses its separate Network RetroPad path; the Linux Controller Router card does not apply. |

Controller Router changes *which player receives input*. It does not change a game's player count, remap buttons in EmulationStation, register ROMs, or turn an ordinary NES game into a native Power Glove game.

## Assign players in Setup

1. Configure each physical gamepad in EmulationStation first. Router reads those saved button mappings and shows the controllers by name and a short identity suffix.
2. Open the live VirtualGlove **Setup** page, select the paired RetroPie, Recalbox, or Batocera console, and find **Controller Router**. Opening the card does not save or change anything.
3. Review each physical controller's suggested or saved player. Choose **Player 1–4** or **Unassigned**. Several physical pads may share one player; one physical pad belongs to only one player.
4. Choose the **VirtualGlove player** if you want joystick gestures in supported FCEUmm or stock Nestopia NES games. Only one player can receive this VirtualGlove. You can leave it unassigned for a physical-only configuration.
5. Close any running RetroArch game, then choose **Save assignments**. Relaunch a game to use the saved routing.

**Player 1 needs a physical controller** for the usual RetroArch menu and exit hotkeys. Setup warns when it has none. VirtualGlove Select remains NES Select and never becomes the physical hotkey. The original pad continues to work in EmulationStation; test the merged pad inside a Libretro game.

## Check controllers and recover a save

Choose **Check controllers**, then press a direction or button on each connected pad during the ten-second test. The result names the responding controls, the saved player, and any unavailable controller. A connected pad with no reported input may simply not have been pressed during the test. **Restore previous assignments** returns to the last saved configuration after a change; close the game before restoring it.

- **Connected:** the saved device is present now.
- **Unavailable:** Router cannot find that saved device. Reconnect the same pad, or configure a replacement in EmulationStation and assign it in Setup.
- **Mapping refreshed:** EmulationStation has a newer valid button map for the same pad. Its player assignment remains; the new map is used at the next game launch.

Router saves a stable controller identity, not a Linux `eventN` or `jsN` number. It resolves the current RetroArch port at launch. A reboot or another USB pad can change device numbers without requiring a new player assignment.

## What happens in a game

Assigned physical pads work immediately in Libretro games. VirtualGlove joystick gestures are admitted only in supported FCEUmm and stock Nestopia NES paths. After a game starts, rest your hand at neutral once; Router discards glove input held in the frontend so it cannot become an accidental first move. Native Super Glove Ball still uses its separate Nestopia (VirtualGlove) input path.

If two physical pads share Player 1, either can control that player. A held button remains active until all sources holding it release. If a pad disconnects, Router releases only that pad's held input. At game exit, Router releases every merged input and returns the physical pads to normal frontend use.

## If the wrong controller responds

**My usual pad works in EmulationStation but not in the game.** Try another connected pad first. Your usual pad may be assigned to Player 2 while another is Player 1. Check the names and slots in Router, run **Check controllers**, then correct the assignment with the game closed.

**A pad is marked Unavailable.** Reconnect that exact pad and test it in EmulationStation. A replacement with a different identity is not silently substituted; assign the replacement explicitly.

**VirtualGlove recognises my hand but the game does not move.** Confirm a supported NES core, the selected VirtualGlove player, active controller delivery, and one fresh neutral hand after game launch. Test a physical pad separately to tell routing from recognition apart.

**Buttons changed after an EmulationStation remap.** Exit and relaunch the game. Router uses the new valid mapping for the saved device without moving it to another player.

For the differences between joystick and native glove input, see [Input Modes](INPUT_MODES.md). For platform-specific failures, see [Troubleshooting by Symptom](TROUBLESHOOTING.md).
