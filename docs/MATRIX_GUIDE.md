# Matrix Display Guide

The blue LED matrix on the **VirtualGlove Controller (Arduino UNO Q)** is
VirtualGlove's status display. It tells
you which mode is active and helps distinguish startup, practice, tracking, and
pairing. It does not show a game's score or confirm that a game accepted a button.

Use the pictures and quick checks below to recognise what is happening and decide what to do next.

## Start here

After reboot, the display shows Router's neutral animation. Start a registered game and the display changes to that app's cues automatically. When the game ends, it returns to neutral.

You can also open the controller address to choose an app while no game is running. Finish a game before pairing or changing apps.

If the display stays neutral during your game, open Dashboard and check the console connection and selected game. You do not need to reinstall just because no game is selected.

## Recognise the display

| What you see | See it | What it means | What to do |
| --- | --- | --- | --- |
| Arduino boot logo | <img src="images/matrix/Boot.jpg" alt="Boot matrix display" width="104"> | The VirtualGlove Controller's system software is starting, before VirtualGlove controls the display. | Wait for the app's hourglass or normal display. |
| System heart animation | <img src="images/matrix/Heart.jpg" alt="Heart matrix display" width="104"> | The board is progressing through system startup. | Wait for the app display. |
| Router’s neutral animation | — | No selected product has an active Matrix request. | Start a registered game or open the controller home page to choose an app. |
| Pulsing hourglass | <img src="images/matrix/Hourglass.jpg" alt="Hourglass matrix display" width="104"> | VirtualGlove is starting. | Allow startup to finish. If it persists, check Dashboard. |
| A large scanning **L** | <img src="images/matrix/L.jpg" alt="L matrix display" width="104"> | Play or Glove Academy lessons are active. L stands for local play or lessons. | Follow the game or practice moves shown in your browser; controller output is paused. |
| A large scanning **T** | <img src="images/matrix/T.jpg" alt="T matrix display" width="104"> | Gesture tuning is active, including hand setup. | Follow the recording, preview, and save instructions in Glove Academy. Controller output is paused. |
| A steady **1-14**, **A-I**, **BS**, or **GB** | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | A game profile is selected, but a calibrated hand is not currently being reported as tracked. | Show your hand and check tracking/calibration on Dashboard. Program 14 intentionally keeps the camera off. |
| **1-13**, **A-I**, **BS**, or **GB** gently changing brightness | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | The app reports a detected, calibrated hand for that profile. | Check Dashboard's controller status before playing. This pulse alone does not mean controls are enabled. |
| **ID**, characters, **PN**, and digits repeating | — | Secure pairing is showing the device identity and temporary PIN. | Follow the Setup page; read each group in order. |
| A flashing **X** | <img src="images/matrix/X.jpg" alt="X matrix display" width="104"> | The app has requested an error display. | Read Dashboard's error message before deciding whether to reconnect the camera or restart. |
| A blank matrix | <img src="images/matrix/Blank.jpg" alt="Blank matrix display" width="104"> | The display has been turned off, the app is stopping, or the board is still starting. It may also have lost power. | Use the browser and board power indicators to distinguish these cases. Blank does not prove shutdown is complete. |

## Local play and Glove Academy: L and T

| L: Local play or Glove Academy lessons | T: Gesture tuning |
| --- | --- |
| <img src="images/matrix/L.jpg" alt="Local play or Glove Academy lessons" width="230"> | <img src="images/matrix/T.jpg" alt="Gesture tuning" width="230"> |

**L** means local Play or Glove Academy lessons are active. **T** means gesture tuning is
active, including **Set up my hand**, individual adjustments, and previews.
Follow the browser's instructions to practice or complete your recordings.

Both modes pause controller output. After practice, use Dashboard to check the
selected profile and controller state; after tuning, explicitly start controller
delivery when ready to play. A pairing display can temporarily cover either
letter. Tracking details and pose failures remain in the browser rather than
being spelled out on the matrix.

## Game profile codes

| Code | See it | Selected profile |
| --- | --- | --- |
| **1** through **13** | Numeric program code | The corresponding original camera-active numeric profile; older firmware safely shows blank |
| **14** | Numeric program code | Program 14 is selected; camera and VirtualGlove output intentionally stay off while the game session remains visible |
| **A** through **I** | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | The corresponding reusable Program A-I profile; A is shown |
| **BS** | <img src="images/matrix/BS.jpg" alt="BS matrix display" width="104"> | Bad Street Brawler |
| **GB** | <img src="images/matrix/GB.jpg" alt="GB matrix display" width="104"> | Super Glove Ball |

For example, **GB** is what you should expect with Super Glove Ball selected.
It stays steady until a calibrated hand is being tracked, then gently pulses. The characters remain the same: the animation does not
identify individual finger curls, movements, or button presses.

The important distinction is **tracking versus delivery**. A pulsing **GB** can
appear while controller output is stopped. Confirm **Start controller** has been
used and Dashboard shows output enabled, then confirm the action in the game.
The matrix does not acknowledge console receipt or the game's response.

A generic **PG** ready symbol or a small pulsing tracking symbol can appear when
no recognised profile identifier is available. These are fallback displays;
normal named game profiles use their numeric, letter, or dedicated two-character
codes. They do not represent extra games
or new gesture commands. If you expected **GB** or **BS**, check the selected
profile on Dashboard.

## Pairing: ID and PN

When a submitted pairing attempt finishes, the matrix releases the approval PIN and resumes its normal display. The selected app resumes its display. With no app selected, Controller Router shows its neutral animation. VirtualGlove’s On, Dim, or Off attract setting applies while VirtualGlove is selected; game and status displays take priority.

During secure pairing, the small display presents the information in pieces:

1. **ID** announces the device certificate identity.
2. Seven hexadecimal characters follow in groups of three, with the last character shown alone.
3. **PN** announces the temporary six-digit PIN.
4. Two groups of three digits follow, preserving leading zeroes.
5. The sequence repeats so you can read it again.

Read each group from left to right and join the groups in the order shown. Do not
mistake **PN** for a game program or use the certificate identity as the PIN.

Follow the Setup page to compare the identifier and enter the PIN. Pairing
information temporarily replaces the usual display. If it expires before you
finish, prepare a new pairing attempt. Check the page for confirmation that
pairing succeeded.

For public photographs, use a clearly marked demonstration sequence or obscure
live pairing digits. Never publish an active PIN or connection credentials. See
[secure pairing](INSTALL_README.md) for the full procedure.

## Errors, pauses, and a blank display

| Flashing X | Blank matrix |
| --- | --- |
| <img src="images/matrix/X.jpg" alt="X: error display. Check Dashboard for the cause." width="230"> | <img src="images/matrix/Blank.jpg" alt="Blank matrix: no LEDs are illuminated." width="230"> |

A blinking **X** means the app needs attention. Read Dashboard's error message
for the cause and the next step. Check Dashboard whenever something is not
working, even if the matrix still shows a normal mode.

A blank display alone does not prove the board is safe to unplug. Use the normal
Shutdown procedure and its completion guidance. If the board should be running,
check its power, wait for boot to finish, and try Dashboard. If the web app works
but the display stays blank, record what appeared immediately before it went
blank and whether restarting the app changes it.

For older standalone display settings and firmware maintenance, see the [Configuration Reference](CONFIGURATION_REFERENCE.md#standalone-matrix-firmware-reference).
