# Choose how VirtualGlove controls your game

Most NES games use **joystick mode**: your gestures act like a gamepad's directions and buttons. Super Glove Ball also offers **native Power Glove mode**, where moving your hand positions the game's Robo-Glove more freely.

You can keep using a physical gamepad in either mode. Your saved hand setup works with both.

## Pick a mode

| What you want to play | Choose |
| --- | --- |
| An ordinary registered NES game | FCEUmm or stock Nestopia, using joystick mode. |
| Super Glove Ball with continuous hand movement | **Nestopia (VirtualGlove)**, using native mode. |
| Super Glove Ball with ordinary directions and buttons | FCEUmm, using joystick mode. |
| A game using only your physical pad for a while | Choose **Gestures off** or **Program 14**. |

For each program's gestures, open the [Game and Gesture Guide](GAMEPLAY_GUIDE.md).

## Try joystick mode

1. Start a registered NES game using FCEUmm or stock Nestopia.
2. Check that your physical pad's directions, buttons, Start, and Select work.
3. Show your hand and rest it at its saved centre once.
4. Move your hand in one direction, then return to centre to release it.
5. Try one button gesture from the selected program.
6. Test your physical pad's usual menu and exit combination.

If the camera loses your hand, VirtualGlove releases its controls. Your physical pad remains available. Use **Stop controller** before moving the camera or changing your playing position.

## Use your gamepad and gestures together

On a console using Controller Router, open [Router Setup](CONTROLLER_ROUTER.md) to assign your pad and VirtualGlove to the same player. You can also assign several physical pads to one player.

Use **Systems** to choose where these player assignments apply. Router can handle physical pads for supported RetroArch systems; glove joystick gestures are for supported NES games. Systems set to **My existing setup** keep their normal controls. Standalone emulators use their own controls.

Keep a physical pad on **Player 1** for menu and exit hotkeys. VirtualGlove's Select gesture is the game's Select button, not an exit hotkey.

A standard RetroPie installation can instead use the separate VirtualGlove gamepad. Recalbox and Batocera use Router. LaunchBox uses its separate Windows controller connection. Follow the [installation guide](INSTALL_README.md) for your platform.

## Play native Super Glove Ball

Native mode gives you these controls:

| Your action | In the game |
| --- | --- |
| Move your hand left, right, up, or down | Move the Robo-Glove through the playfield. |
| Close your hand | Grab or catch. |
| Open your hand | Release or throw. |
| Point with your index finger | Fire Robo-Bullets. |
| Make a fist and push forward | Power Punch. |
| Use the Start gesture or physical Player 1 Start | Start the game. |

To get started:

1. Register your Super Glove Ball filename in VirtualGlove Setup.
2. Check that the console installation reports **Nestopia (VirtualGlove)** as available.
3. Select that emulator for Super Glove Ball if the console kept an earlier choice.
4. Launch the game.
5. On Dashboard, check the selected player and saved hand centre, then choose **Start controller** if delivery is stopped.
6. Use Start, then practise moving, catching, and throwing before adding fire and Power Punch.

To return to joystick mode, choose FCEUmm for the game. You do not need to recalibrate or change your ROM.

Native mode is supported for the registered Super Glove Ball game with its special Nestopia core. Other games and ordinary Nestopia use joystick mode. If the native core is unavailable, use FCEUmm while you check the console installation.

## When controls feel wrong

**The Robo-Glove moves like a D-pad.** Check the game's emulator choice. Continuous movement needs **Nestopia (VirtualGlove)**.

**My hand is visible but nothing moves.** Check the selected player, saved centre, and **Start controller** state. Close local Play, lessons, or tuning, which pause game input. In joystick mode, rest your hand at centre once after launching.

**My pad works in the menu but not in the game.** Try another pad, then check the player assignments in Router Setup with the game closed.

**My buttons changed.** Confirm the buttons in EmulationStation, then exit and relaunch the game.

**Super Glove Ball did not detect the glove.** Confirm the registered filename and special emulator choice, then exit and relaunch the game.

See [Troubleshooting](TROUBLESHOOTING.md) for the next check. Developers can find packet formats, freshness rules, and compatibility evidence in the [Configuration Reference](CONFIGURATION_REFERENCE.md) and [Game Input Audit](power-glove-rom-input-audit.md).
