# Play with VirtualGlove

The **VirtualGlove Controller (Arduino UNO Q)** watches your hand and sends
the recognized controls to RetroPie.

This guide provides game-specific play cards and explains how to use the
original Programs 1–14 and cartridge Programs A–I. It shows you which gestures to make, what controls
they produce, and how to try them with other games in your library.

Find your game below, check its profile, and try the first-round exercise.
If the system is not installed yet, start with the [Installation Guide](INSTALL_README.md).

## Play Rock Paper Scissors locally

Open **Play** at `http://UNO-Q-NAME.local:8088/play` for a first-to-three match
against Pixel Pal. This local game uses the Controller camera and pauses cabinet
input while the page is open, so RetroPie does not need to be connected.

| Your move | Make this pose | See it |
| --- | --- | --- |
| Rock | Close all five fingers into a comfortable fist. | <img src="images/gestures/v2/closed-hand.png" alt="Six-digit closed glove for rock" width="96"> |
| Paper | Face an open, relaxed palm toward the camera. | <img src="images/gestures/v2/show-your-hand.png" alt="Open palm for paper" width="96"> |
| Scissors | Extend the index and middle fingers in a V sign. | <img src="images/gestures/v2/v-sign.png" alt="V sign for scissors" width="96"> |

Select **Start round**, follow the countdown, and hold the pose after **Shoot!**
until its button is highlighted. The first player to win three rounds takes the
match. Mouse and touch buttons remain available if the camera is unavailable.

![Local Rock Paper Scissors, with the camera preview omitted in this documentation example.](images/play-page.png)

## Get ready to play

Choose your player in **Active player** so practice and sensitivity changes belong
to you. Select a profile on Dashboard and wait for the camera view. Starting
straight after a reboot can take longer.

1. Stand where the camera can see your whole hand, with room to move on every side.
2. Face a relaxed open palm toward the camera. On first use, or after moving the camera or changing your playing position, select **Center hand** and hold still until it finishes. Otherwise use your saved resting position.
3. Select **Start controller** when ready. If the tracker is reconnecting, Start remains pending until it can be delivered; **Stop controller** cancels that request.
4. Launch a registered game and allow its short startup pause to finish. Check the selected profile on Dashboard against the play card below; the card also shows its matrix display.
5. Try one gesture at a time. Return to your resting position between attempts. In standard movement profiles this stops directional input; Nestopia (VirtualGlove) follows your hand's position continuously.

**Start controller** stays armed across Controller restarts, but sends controls
only while a registered game or a manually selected Dashboard profile is active.
Exiting the game or losing its session releases controls. **Stop controller**
keeps delivery stopped until you explicitly start it again. Use it before
repositioning yourself or the camera.

### Read the camera view

The overlay labels the detected hand **Right** or **Left** and shows the tracker's
confidence. Dashboard's D-pad, button, and axis readings show the controls your
hand produces. Keep your whole hand visible and use small, comfortable movements.
If your resting hand causes unwanted movement, recalibrate in that position.

<img src="images/gestures/v2/pixel-pal-ready.png" alt="Pixel Pal takes a ready-to-play stance" width="150">

> **Pixel Pal's Extra-Digit Hunt:** Some glove illustrations have five fingers
> plus a thumb. Count every six-digit hand once per appearance, including
> repeated artwork. Pixel Pal reveals the answer at the back of this guide.

## Practise with Glove Academy

Open **Glove Academy** from the main navigation to practise with Pixel Pal.
Cabinet controller output pauses while you learn. The sixteen lessons cover
showing your hand, finding your resting position, four movement directions,
index and thumb curls, Start and Select poses, forward and backward movement,
wrist rolls, a closed hand, and Menu guard.

Complete all sixteen lessons to earn **Glove Master**. The award replaces the
lesson card. Progress is saved for the selected player across browsers and
restarts; **Start again** clears that player's saved lesson progress and returns
to the lessons. It does not clear their hand settings.

Glove Academy practises recognition, not each game's button assignments.
Use the gesture reference next, then your game's play card. For a difficult
pose, see [Make the controls fit your hand](#make-the-controls-fit-your-hand).

<!-- PAGEBREAK -->

## Your gesture reference

Practice one movement at a time in **Glove Academy**. Your selected profile
decides what each gesture does in a game; the play cards below show the mapping.
This reference also includes game-specific finger poses and combinations beyond
the sixteen Academy lessons. The glove is an illustration: the Controller
tracks your bare hand.

### Resting position and movement

| Gesture | See it | Try it |
| --- | --- | --- |
| Show an open hand | <img src="images/gestures/v2/show-your-hand.png" alt="Open palm facing the camera" width="88"> | Open your fingers comfortably and keep your whole palm visible. |
| Find your resting position | <img src="images/gestures/v2/find-neutral.png" alt="Relaxed hand at the movement centre" width="88"> | Hold a relaxed open hand at your saved centre and distance. |
| Move left | <img src="images/gestures/v2/move-left.png" alt="Move left" width="88"> | Slide your whole hand left. |
| Move right | <img src="images/gestures/v2/move-right.png" alt="Move right" width="88"> | Slide your whole hand right. |
| Move up | <img src="images/gestures/v2/move-up.png" alt="Move up" width="88"> | Raise your whole hand. |
| Move down | <img src="images/gestures/v2/move-down.png" alt="Move down" width="88"> | Lower your whole hand. |

With an ordinary FCEUmm joystick profile, combine horizontal and vertical movement
for diagonals. Your box is anchored to the hand center you saved during calibration;
inside it—or exactly on its boundary—all positional directions stop immediately.
Its effective size is never less than 1.5 times your saved hand size. Change its
chosen size in Setup.

### Wrist and depth movements

| Gesture | See it | Try it |
| --- | --- | --- |
| Roll wrist left | <img src="images/gestures/v2/wrist-roll-left.png" alt="Roll wrist left" width="88"> | Tilt your hand left at the wrist. |
| Roll wrist right | <img src="images/gestures/v2/wrist-roll-right.png" alt="Roll wrist right" width="88"> | Tilt your hand right at the wrist. |
| Push toward camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push toward camera" width="88"> | Push deliberately, then return. Holding your hand nearby does not trigger a new Glove Zap. |
| Pull away from camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull away from camera" width="88"> | Pull away deliberately, then return. Holding your hand far away does not trigger a new Pull Back. |

<!-- PAGEBREAK -->

### Finger and hand poses

| Gesture | See it | Try it |
| --- | --- | --- |
| Curl index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl index finger" width="88"> | Bend your index finger toward your palm. |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl thumb" width="88"> | Fold your thumb across your palm. |
| Curl middle finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove illustrating a finger curl" width="88"> | Bend your middle finger toward your palm; used in Bad Street Brawler and Joust. |
| Curl ring finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove illustrating a finger curl" width="88"> | Bend your ring finger toward your palm; used in Defender II. |
| Close your hand | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing every finger into a fist" width="88"> | Curl your thumb and all four fingers into a comfortable fist. |
| Keep index straight | <img src="images/gestures/actions/keep-index-straight.png" alt="Extended index finger" width="88"> | Keep your index finger extended for Gyruss fire. |
| Point index | <img src="images/gestures/actions/keep-index-straight.png" alt="Index-point pose" width="88"> | Extend index and curl middle, ring, and pinky for the native Super Glove Ball Robo-Bullet. |

### Menu poses

| Gesture | See it | Try it |
| --- | --- | --- |
| V sign | <img src="images/gestures/v2/v-sign.png" alt="V sign with index and middle extended" width="88"> | Extend index and middle, curl ring and pinky, and hold steadily for about half a second for Start or pause. |
| Thumbs-up | <img src="images/gestures/v2/thumbs-up.png" alt="Thumbs-up with four fingers closed" width="88"> | Extend your thumb, close all four fingers, and hold until Select is recognized. |
| Menu guard | <img src="images/gestures/actions/menu-guard.png" alt="Menu guard with thumb and ring finger curled" width="88"> | Curl thumb and ring only; keep index, middle, and pinky extended. |

Start and Select send controller inputs; their effect depends on the game.
The V sign and thumbs-up suppress A/B actions while forming, but some profiles
can still produce movement. Keep your hand near its resting position. Use a
physical controller if a game requires Select and a direction together.

Menu guard suppresses D-pad, A/B, Start, and Select, and cancels a pending Start
press. It does **not** freeze native continuous hand positioning. For a dependable
pause in all controller delivery while you reposition, use **Stop controller**.

<!-- PAGEBREAK -->

## Quick selector - Programs 1–14

These profiles reproduce the built-in Power Glove programs with camera gestures
and ordinary NES controller output. Rapid fire defaults on only where an
individual program description explicitly identifies a rapid or pulsed action.
Among Programs 1–14, that means Program 7 starts with Rapid A on; the remaining
numbered programs start with held A/B controls. Program 14 stops camera tracking
and sends no VirtualGlove input so a conventional controller can be used without
ending the authenticated game session.

| Program | See it | Core controls | Games in Mattel's index |
| --- | --- | --- | --- |
| 1 | <img src="images/matrix/programs/1.png" alt="1 matrix display illustration" width="104"> | Hand position is the D-pad; thumb is A; index is B; curling the last three fingers performs one bounded turn-and-B action. | Blades of Steel; Blaster Master; Bubble Bobble; Castlevania; Castlevania II: Simon's Quest; Contra; Deadly Towers; Donkey Kong Classics; Double Dribble; Gauntlet; Gradius; Jackal; Kid Icarus; Kung-Fu Heroes; Metal Gear; Metroid; Mickey Mousecapade; Operation Wolf; Platoon; Racket Attack; Rampage; RoboWarrior; Rygar; Seicross; Star Force; Superman; Xenophobe; Zelda II: The Adventure of Link |
| 2 | <img src="images/matrix/programs/2.png" alt="2 matrix display illustration" width="104"> | Program 1 movement and buttons, plus live **Centered** / **Return to centre** feedback in place of the physical glove's beeper. | Centering-practice alternative; no indexed title |
| 3 | <img src="images/matrix/programs/3.png" alt="3 matrix display illustration" width="104"> | Push / pull sends Up / Down; side movement sends Left / Right; thumb / index sends A / B. | Ice Hockey; Top Gun. Gauntlet may also use this as an alternative top-view layout, although the index assigns it to Program 1. |
| 4 | <img src="images/matrix/programs/4.png" alt="4 matrix display illustration" width="104"> | Open or close all four fingers for Up / Down; index-versus-last-three poses steer the treads; thumb sends A; wrist poses send held B or Up plus Left / Right. | Iron Tank |
| 5 | <img src="images/matrix/programs/5.png" alt="5 matrix display illustration" width="104"> | Push / pull and bank / side movement fly the craft; thumb / index sends A / B. | Alpha Mission; Life Force; Xevious; 1943 |
| 6 | <img src="images/matrix/programs/6.png" alt="6 matrix display illustration" width="104"> | Position and depth move; index sends A; thumb sends B; last three sends A+B; forward fist holds Up; clockwise twist turns rapidly twice. | Double Dragon |
| 7 | <img src="images/matrix/programs/7.png" alt="7 matrix display illustration" width="104"> | Open-hand movement dodges and ducks; forward fists punch high or low; clockwise wrist blocks; pull-back fist sends Select; thumb sends rapid A. | Mike Tyson's Punch-Out!! |
| 8 | <img src="images/matrix/programs/8.png" alt="8 matrix display illustration" width="104"> | Position and depth select bases or fielding direction; thumb, index, counter-clockwise wrist, and pull-back produce the documented offense / defense A and B actions. | Baseball; Bases Loaded; R.B.I. Baseball |
| 9 | <img src="images/matrix/programs/9.png" alt="9 matrix display illustration" width="104"> | Make a fist to ready the profile. Wrist rotation steers; forward fist is turbo; raising the hand sends Down; lowering sends B; fist sends A. No rapid fire. | Rad Racer |
| 10 | <img src="images/matrix/programs/10.png" alt="10 matrix display illustration" width="104"> | Index / last-three curls steer Left / Right; thumb sends A; B is held automatically until the hand is lowered. | R.C. Pro-Am |
| 11 | <img src="images/matrix/programs/11.png" alt="11 matrix display illustration" width="104"> | Program 1 controls, but the last-three-finger pose turns rapidly in both directions while firing B. | Fast-turn alternative; no indexed title |
| 12 | <img src="images/matrix/programs/12.png" alt="12 matrix display illustration" width="104"> | Position moves Mario; thumb holds A for controllable jumps; index sends B; middle curl adds B for fast travel; last-three curl slows horizontal travel. | Super Mario Bros. |
| 13 | <img src="images/matrix/programs/13.png" alt="13 matrix display illustration" width="104"> | Thumb / index sends A / B. Camera D-pad output is neutral, leaving movement and menus to a conventional controller. | No indexed title |
| 14 | <img src="images/matrix/programs/14.png" alt="14 matrix display illustration" width="104"> | VirtualGlove camera and output are paused while the selected profile and game session remain visible. | Anticipation; temporary manual menu or password entry |

The shipped exact-filename registry supplies `.nes`, `.zip`, and `.7z` entries.
It retains Mattel's explicit rapid-fire-off entries for Alpha Mission, Blaster
Master, Ice Hockey, Double Dribble, and Racket Attack. These entries are now
redundant with the source-accurate profile defaults, but preserve the official
game-specific instructions if a profile default changes later.

<!-- PAGEBREAK -->

## How rapid fire behaves

**Original-hardware source note:** Mattel's *Power Glove Instructions*, page 14,
states, “Rapid Fire for both A and B turns on automatically when you turn on the
glove.” The same page immediately warns that not every glove program has rapid
fire and directs players to the individual program descriptions. VirtualGlove
therefore does not reproduce that blanket power-on state: it uses the documented
behavior of the active profile instead.

Rapid A/B defaults come from the individual program descriptions rather than the
manual's general power-on behavior. Program 7 defaults to Rapid A; Program B
defaults to Rapid A for its pulsed flap; Program H defaults to both; and Bad
Street Brawler defaults to Rapid B for its pulsed thumb action. Every other
profile starts with A and B held. Documented compound, pulsed-direction, and
turbo actions keep their own timing independently of these switches.

In VirtualGlove, **Rapid A** and **Rapid B** mean only that the corresponding NES
button repeats while its gesture remains active. A profile's fast turns, pulsed
steering, turbo movement, simultaneous-button combinations, and other compound
actions are part of that profile and do not change when these two switches are
changed.

Program 12 therefore holds A for as long as the thumb stays curled, allowing
variable-height jumps in Super Mario Bros. If Rapid A is explicitly enabled on
Dashboard, it repeats 250 ms A holds separated by a short rapid-fire gap. A
registered game's settings travel in its signed launch request, and Dashboard's
**Rapid fire** status shows the values actually applied to the running game.

**After an upgrade:** explicit Rapid A/B choices already saved for a game remain
in force and override the corrected profile defaults. On Dashboard, choose
**Use profile defaults** if you want that game to follow the source-accurate
defaults again. This removes only its Rapid A/B override; it does not change the
game's profile or any player settings.

| Game | Program | Automatic exception | Why it matters while playing |
| --- | --- | --- | --- |
| Blaster Master | 1 | Rapid A off | A can be held continuously while thumb curl remains active. |
| Double Dribble | 1 | Rapid A and B off | Both finger buttons behave as held controls. |
| Racket Attack | 1 | Rapid A and B off | Both finger buttons behave as held controls. |
| Ice Hockey | 3 | Rapid B off | Retains Mattel's explicit held-B instruction. |
| Alpha Mission | 5 | Rapid A off | Retains Mattel's explicit held-A instruction. |

Start, Select, Menu Guard, calibration, tracking-loss release, and the saved
joystick dead zone remain shared across every camera-active numeric Program.
Return to an open hand near the saved center between compound actions.

<!-- PAGEBREAK -->

## Program cards 1–14

Each card follows the same design as the game-specific cards: the exact
Dashboard profile and matrix display, a mission, illustrated controls, practical
play advice, and a first-round exercise. Programs without an official indexed
title remain complete, selectable profiles and are especially useful for
off-script experiments.

### Program 1 - positional control

| Profile | See it |
| --- | --- |
| `program_1` | <img src="images/matrix/programs/1.png" alt="1 matrix display illustration" width="104"> |

**Your mission:** Use the original all-purpose mapping to move in every
direction, operate both action buttons, and learn its bounded turn-and-fire
combination.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand around its saved center" width="96"> | Ordinary D-pad, including diagonals |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |
| Curl middle, ring, and pinky together | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers together" width="72"> | Briefly turns opposite the last horizontal direction and sends B |
| Return to the saved center | <img src="images/gestures/v2/find-neutral.png" alt="Relaxed hand at the saved center" width="72"> | Releases positional movement |

**Play smart:** The turn-and-B combination lasts about 0.18 seconds and triggers
once per fresh last-three-finger pose. Release those fingers before trying it
again. A and B are held by default; a registered game can still opt into rapid
behavior from Dashboard. The complete official Program 1 game list is in the numbered
[Quick selector](#quick-selector-programs-1-14).

**First round:**

1. Move across all four sides of the saved center and return to neutral.
2. Try thumb A and index B separately.
3. Curl the last three fingers once, release them, and confirm the bounded turn-and-B action ends.

<!-- PAGEBREAK -->

### Program 2 - positional control with centering feedback

| Profile | See it |
| --- | --- |
| `program_2` | <img src="images/matrix/programs/2.png" alt="2 matrix display illustration" width="104"> |

**Your mission:** Keep an exact sense of neutral while using Program 1's
movement, buttons, and bounded turn-and-fire action in an unassigned game.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand around its saved center" width="96"> | Ordinary D-pad, including diagonals |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |
| Curl middle, ring, and pinky together | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers together" width="72"> | Briefly turns opposite the last horizontal direction and sends B |
| Return to the saved center | <img src="images/gestures/v2/find-neutral.png" alt="Relaxed hand at the saved center" width="72"> | Releases movement and shows **Centered**; leaving the box shows **Return to centre** |

**Play smart:** Program 2 has no indexed title and is the centering-practice
alternative to Program 1. Dashboard's live feedback replaces the physical
glove's beeper and stores no new centering measurement. Its turn-and-B action
uses the same 0.18-second fresh-pose and release rules.

**First round:**

1. Rest inside the saved box and confirm Dashboard shows **Centered**.
2. Cross one side of the box, return until **Centered** reappears, then repeat on the other sides.
3. Try A, B, and one released turn-and-B action without losing the neutral reference.

<!-- PAGEBREAK -->

### Program 3 - depth and side movement

| Profile | See it |
| --- | --- |
| `program_3` | <img src="images/matrix/programs/3.png" alt="3 matrix display illustration" width="104"> |

**Your mission:** Combine sideways hand travel with deliberate push/pull depth
control for Ice Hockey, Top Gun, or a similar top-view game.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move left or right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move the whole hand left or right" width="96"> | Left or Right |
| Push toward the camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push the hand toward the camera" width="72"> | Up |
| Pull away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull the hand away from the camera" width="72"> | Down |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |

**Play smart:** Use Program 3 for **Ice Hockey** and **Top Gun**. Ice Hockey
automatically disables rapid B. Mattel also described Program 3 as an
alternative top-view scheme for Gauntlet, but the official index and shipped
registry assign Gauntlet to Program 1.

**First round:**

1. Move left and right while keeping a steady camera distance.
2. Push once for Up, return to neutral depth, then pull once for Down.
3. Add thumb A and index B only after the four directions release reliably.

<!-- PAGEBREAK -->

### Program 4 - Iron Tank tread control

| Profile | See it |
| --- | --- |
| `program_4` | <img src="images/matrix/programs/4.png" alt="4 matrix display illustration" width="104"> |

**Your mission:** Drive Iron Tank with finger-tread poses, fire independently,
and use the higher-priority wrist actions without leaving a direction held.

Program 4 does not use ordinary camera-position D-pad movement. Its finger and
wrist poses drive the tank directly, in the following priority order.

| Do this | See it | Controller result |
| --- | --- | --- |
| Keep index, middle, ring, and pinky open | <img src="images/gestures/v2/show-your-hand.png" alt="Open four fingers" width="72"> | Up |
| Curl all four fingers | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling all four fingers" width="72"> | Down |
| Keep index open and curl the last three; or curl index and keep the last three open | <img src="images/gestures/actions/keep-index-straight.png" alt="Keep the index open and curl the last three fingers" width="60"> <img src="images/gestures/v2/curl-index.png" alt="Curl only the index finger" width="60"> | Right tread turn; or Left tread turn, respectively |
| Roll wrist right or left | <img src="images/gestures/v2/wrist-roll-right.png" alt="Roll the wrist right" width="60"> <img src="images/gestures/v2/wrist-roll-left.png" alt="Roll the wrist left" width="60"> | Up+Right; or Up+Left, respectively |
| Turn the wrist almost upside down | <img src="images/gestures/actions/wrist-roll.png" alt="Rotate the wrist close to upside down" width="96"> | B |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A alongside the active movement, except while pulling back |
| Pull away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull away from the camera" width="72"> | Neutralizes the Program 4 action output |

**Play smart:** Program 4 is assigned to **Iron Tank**. Release a wrist pose
before changing to a finger-tread pose so the higher-priority wrist action
clears first. Pulling back is the dependable way to neutralize its special
action output.

**First round:**

1. Test open-four Up and closed-four Down, returning to a relaxed hand between them.
2. Try each asymmetric tread pose separately.
3. Add thumb fire, then practise each wrist action and pull back to neutralize it.

<!-- PAGEBREAK -->

### Program 5 - aircraft control

| Profile | See it |
| --- | --- |
| `program_5` | <img src="images/matrix/programs/5.png" alt="5 matrix display illustration" width="104"> |

**Your mission:** Fly with horizontal movement, wrist bank, and depth while
keeping both firing gestures available.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move or bank left/right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move or roll left whole hand left or right" width="96"> | Left or Right; a wrist bank can add the same direction |
| Push toward the camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push toward the camera" width="72"> | Up |
| Pull away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull away from the camera" width="72"> | Down |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |

**Play smart:** Use Program 5 for **Alpha Mission**, **Life Force**, **Xevious**,
and **1943: The Battle of Midway**. Keep the wrist level when you want plain
side movement; a bank can reinforce the same direction. Alpha Mission
automatically disables rapid A.

**First round:**

1. Fly left and right with a level wrist.
2. Push and pull once each, returning to the saved distance after both actions.
3. Add thumb A, index B, and then a small wrist bank while moving.

<!-- PAGEBREAK -->

### Program 6 - Double Dragon combinations

| Profile | See it |
| --- | --- |
| `program_6` | <img src="images/matrix/programs/6.png" alt="6 matrix display illustration" width="104"> |

**Your mission:** Chain Double Dragon's movement, single-button attacks,
combined attack, forward-fist action, and bounded turning combination without
carrying one pose into the next.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move left/right; push/pull | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move sideways or in depth" width="96"> | Left/Right; push is Up and pull is Down |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | A |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | B |
| Curl middle, ring, and pinky together | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers" width="72"> | A+B |
| Make a fist and push | <img src="images/gestures/v2/push-closed-fist.png" alt="Push a closed fist toward the camera" width="72"> | Up only; A and B release |
| Roll wrist right | <img src="images/gestures/v2/wrist-roll-right.png" alt="Roll the wrist right" width="72"> | A bounded four-phase Left/Right/Left/Right turn over about 0.32 seconds |

**Play smart:** Program 6 is assigned to **Double Dragon**. The wrist
combination begins on a fresh right-roll hold; release the roll before repeating
it. The pushed fist deliberately releases A and B while holding Up.

**First round:**

1. Walk in four directions, then test index A and thumb B separately.
2. Curl the last three fingers for A+B and fully reopen them.
3. Try one pushed fist and one right-roll combination, returning to neutral after each.

<!-- PAGEBREAK -->

### Program 7 - Punch-Out!! offense and defense

| Profile | See it |
| --- | --- |
| `program_7` | <img src="images/matrix/programs/7.png" alt="7 matrix display illustration" width="104"> |

**Your mission:** Use open-hand defense and positioned fist attacks to complete
a controlled round in Mike Tyson's Punch-Out!!.

| Do this | See it | Controller result |
| --- | --- | --- |
| With four fingers open, move left/right or lower the hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move an open hand left, right, or down" width="96"> | Dodge Left/Right or duck Down |
| With four fingers open, curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb while the fingers stay open" width="72"> | Rapid A |
| Make a fist, push, and hold it right of center | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing every finger into a fist" width="60"> <img src="images/gestures/v2/push-closed-fist-right.png" alt="Push a closed fist on the right side of center" width="60"> | A punch; raising it above center adds Up for a high punch |
| Make a fist, push, and hold it left of center | <img src="images/gestures/v2/push-closed-fist-left.png" alt="Push a closed fist on the left side of center" width="88"> | B punch; raising it above center adds Up for a high punch |
| Roll wrist right | <img src="images/gestures/v2/wrist-roll-right.png" alt="Roll the wrist right" width="72"> | Down block |
| Make a fist and pull back | <img src="images/gestures/v2/pull-closed-fist.png" alt="Pull a closed fist away from the camera" width="88"> | One Select pulse for the star-punch action |

**Play smart:** Program 7 is assigned to **Mike Tyson's Punch-Out!!** and is the
only numbered Program whose individual description explicitly calls for a
rapid button default. Keep the
fist clearly left or right of center so the intended punch is unambiguous. The
pull-back Select is edge-triggered: return from the pull before requesting
another star punch.

**First round:**

1. With an open hand, dodge left and right and lower the hand to duck.
2. Push a fist on each side for low punches, then raise it for high punches.
3. Practise one wrist block and one pull-back star-punch pulse.

<!-- PAGEBREAK -->

### Program 8 - baseball offense and defense

| Profile | See it |
| --- | --- |
| `program_8` | <img src="images/matrix/programs/8.png" alt="8 matrix display illustration" width="104"> |

**Your mission:** Learn when the baseball mapping changes the thumb from B to
direction-plus-A, then use the same profile for batting, running, and fielding.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move left/right; push/pull | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move sideways or in depth" width="96"> | Left/Right; push is Up and pull is Down |
| Curl the thumb while stationary | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb while stationary" width="72"> | B |
| Curl the thumb while moving | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb while moving" width="72"> | A alongside the active direction |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |
| Roll wrist left | <img src="images/gestures/v2/wrist-roll-left.png" alt="Roll the wrist left" width="72"> | B |
| Pull away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull away from the camera" width="72"> | Down+B |

**Play smart:** Use Program 8 for **Baseball**, **Bases Loaded**, and **R.B.I.
Baseball**. The same thumb pose intentionally changes button meaning depending
on whether a direction is active. Establish movement first, then add the thumb
when you need direction-plus-A.

**First round:**

1. Move in each direction with an open thumb and return to neutral.
2. Curl the thumb while stationary to confirm B.
3. Move and curl the thumb for direction-plus-A, then test index B and pull-back Down+B.

<!-- PAGEBREAK -->

### Program 9 - Rad Racer

| Profile | See it |
| --- | --- |
| `program_9` | <img src="images/matrix/programs/9.png" alt="9 matrix display illustration" width="104"> |

**Your mission:** Arm the Rad Racer profile, steer by wrist angle, and combine
its held throttle, turbo, brake, and unusual raise-to-Down mapping.

Program 9 begins unready. Make one fist to arm it; Dashboard then shows the
ready state for the remainder of that profile session. It has no rapid fire.

| Do this | See it | Controller result after arming |
| --- | --- | --- |
| Roll wrist left/right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Steer Left/Right |
| Keep a fist closed | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove holding a closed fist" width="72"> | A |
| Push the closed fist | <img src="images/gestures/v2/push-closed-fist.png" alt="Push a closed fist toward the camera" width="72"> | Up+A turbo combination |
| Raise the hand | <img src="images/gestures/v2/move-up.png" alt="Raise the hand" width="72"> | Down |
| Lower the hand | <img src="images/gestures/v2/move-down.png" alt="Lower the hand" width="72"> | B |

**Play smart:** Program 9 is assigned to **Rad Racer**. Its unusual
raise-to-Down mapping is intentional and follows the documented program rather
than the general movement convention. All inputs are held rather than pulsed.

**First round:**

1. Make one fist and confirm the profile becomes ready.
2. Hold the fist for A and make small wrist rolls to steer.
3. Push the fist for turbo, then separately raise for Down and lower for B.

<!-- PAGEBREAK -->

### Program 10 - R.C. Pro-Am

| Profile | See it |
| --- | --- |
| `program_10` | <img src="images/matrix/programs/10.png" alt="10 matrix display illustration" width="104"> |

**Your mission:** Drive R.C. Pro-Am using finger-tread steering while hand
height controls the automatically held B action.

| Do this | See it | Controller result |
| --- | --- | --- |
| Curl only the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Left |
| Keep index open; curl middle, ring, and pinky | <img src="images/gestures/actions/keep-index-straight.png" alt="Keep index open and curl the last three fingers" width="72"> | Right |
| Make both steering poses at once | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling all four fingers" width="72"> | Steering releases rather than pressing both directions |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Keep the hand above the lower movement region | <img src="images/gestures/v2/find-neutral.png" alt="Keep the hand at or above center" width="72"> | B is held automatically |
| Lower the hand outside the center box | <img src="images/gestures/v2/move-down.png" alt="Lower the hand" width="72"> | Releases B |

**Play smart:** Program 10 is assigned to **R.C. Pro-Am**. Hand position does
not steer; use the two mutually exclusive finger poses. Curling both steering
patterns releases direction instead of sending an impossible Left+Right pair.

**First round:**

1. Keep the hand above the lower region and confirm B is held.
2. Alternate the index-only and last-three steering poses, reopening between them.
3. Lower the hand to release B, then add thumb A when the steering feels reliable.

<!-- PAGEBREAK -->

### Program 11 - rapid turn alternative

| Profile | See it |
| --- | --- |
| `program_11` | <img src="images/matrix/programs/11.png" alt="11 matrix display illustration" width="104"> |

**Your mission:** Apply Program 1's familiar movement and buttons to an
unassigned game, then decide whether its sustained alternating turn-and-B
action fits the game's mechanics.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand around its center" width="96"> | Ordinary D-pad, including diagonals |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |
| Curl middle, ring, and pinky together | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers" width="72"> | Overrides positional movement, alternates Left and Right, and sends B while held |

**Play smart:** Program 11 has no indexed title. It is a Program 1-style
alternative for games where a sustained rapid-turn action is useful. Unlike
Program 1's short turn, the alternating turn continues until the last three
fingers are released, so test it briefly before relying on it.

**First round:**

1. Confirm ordinary hand-position movement and thumb/index buttons first.
2. Curl the last three fingers for a short fast-turn burst.
3. Reopen fully and verify movement and B release before trying a longer burst.

<!-- PAGEBREAK -->

### Program 12 - Super Mario Bros.

| Profile | See it |
| --- | --- |
| `program_12` | <img src="images/matrix/programs/12.png" alt="12 matrix display illustration" width="104"> |

**Your mission:** Move Mario with hand position, combine action buttons for
running and jumping, and deliberately switch between fast and slow travel.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand around its center" width="96"> | Ordinary D-pad |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Hold A for as long as the thumb remains curled |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |
| Curl the middle finger without curling all three last fingers | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling the middle finger" width="72"> | B for fast travel |
| Curl middle, ring, and pinky together while moving sideways | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers while moving" width="72"> | Pulses only the active horizontal direction for slower travel; vertical movement is unchanged |

**Play smart:** Program 12 is assigned to **Super Mario Bros.** Rapid A is off
by default, so jump height follows how long the thumb remains curled. If you
manually enable Rapid A, a held thumb repeats 250 ms A presses separated by a
short gap. Use middle curl
for fast travel and the last-three pose only while you want slower horizontal
movement. Release the last-three pose to return immediately to ordinary travel.

**First round:**

1. Walk in both directions, vary the length of the thumb curl to compare jump heights, and try index B separately.
2. Curl the middle finger while moving to practise fast travel.
3. Use the last-three pose during a safe horizontal stretch, then reopen to restore full movement.

<!-- PAGEBREAK -->

### Program 13 - finger buttons with physical movement

| Profile | See it |
| --- | --- |
| `program_13` | <img src="images/matrix/programs/13.png" alt="13 matrix display illustration" width="104"> |

**Your mission:** Split Player 1 cleanly between gesture action buttons and the
merged physical controller's movement and menus.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move the hand anywhere | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand" width="96"> | No camera D-pad output |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | B |

**Play smart:** Program 13 has no indexed title. Use it when VirtualGlove should
provide the two action buttons while the merged physical Player 1 controller
supplies movement or menu combinations. Shared gesture Start, Select, and Menu
Guard remain available, but camera movement never sends a D-pad direction.

**First round:**

1. Move the physical controller in all four directions and confirm hand movement stays neutral.
2. Keep the physical controller centered and try thumb A and index B separately.
3. Combine one physical direction with one gesture button, then release both.

<!-- PAGEBREAK -->

### Program 14 - gestures off for the active game

| Profile | See it |
| --- | --- |
| `program_14` | <img src="images/matrix/programs/14.png" alt="14 matrix display illustration" width="104"> |

**Your mission:** Pause every VirtualGlove gesture safely while keeping the
authenticated game session and physical Player 1 controller available.

| Do this | See it | Controller result |
| --- | --- | --- |
| Select Program 14 | <img src="images/matrix/programs/14.png" alt="14 matrix display illustration" width="104"> | Camera tracking stops and every VirtualGlove control releases |
| Use the physical Player 1 controller | <img src="images/gestures/v2/find-neutral.png" alt="Relaxed hand while the physical controller is used" width="72"> | Physical D-pad and buttons remain available |
| Select any camera-active profile | <img src="images/gestures/v2/show-your-hand.png" alt="Show the hand after selecting a camera-active profile" width="72"> | Recognition starts again using saved calibration |

**Play smart:** Program 14 is assigned to **Anticipation** and can be selected
temporarily for manual menu or password entry. It preserves the visible profile
and authenticated game session but neutralizes VirtualGlove D-pad, A, B, Start,
and Select. No calibration or player data is erased.

**First round:**

1. Select Program 14 and confirm the camera closes and Dashboard controls are neutral.
2. Complete one menu action with the physical Player 1 controller.
3. Select a camera-active profile and confirm recognition returns with the saved player calibration.

<!-- PAGEBREAK -->


## Programs A-I

The original Power Glove could load nine reusable mappings from Bad Street
Brawler and retain one while the player changed cartridges. VirtualGlove
keeps all nine available at once: choose one on Dashboard or let RetroPie select
one from the registered ROM filename. These mappings produce ordinary NES
controller inputs, so they can be tried with games beyond the tested play cards.

## Where the programs came from

Bad Street Brawler contained nine configuration programs labelled A through I.
The player loaded one into the Power Glove, switched off the NES, swapped to a
different cartridge within roughly 30 seconds, and kept using the downloaded
mapping.

These programs were not replacement firmware. They were small configurations
for the glove's resident gesture interpreter. Each program mapped hand position, depth, wrist angle, and finger bends to
ordinary NES controller inputs. The
next game therefore did not need special Power Glove support.

VirtualGlove keeps all nine profiles ready at once. Select one on
Dashboard or let RetroPie choose it when a game launches. You do not need to
open Bad Street Brawler first.

## Quick selector - Programs A–I

| Program | See it | Best fit | Main controls |
| --- | --- | --- | --- |
| **A** | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> | Pinball | Two finger flippers, wrist tilt, combined-flipper mode |
| **B** | <img src="images/matrix/programs/B.png" alt="B matrix display illustration" width="104"> | Joust | Pulsed steering by position; curl a finger for a pulsed flap |
| **C** | <img src="images/matrix/programs/C.png" alt="C matrix display illustration" width="104"> | Gyruss | Rotate by wrist angle; fire and bomb gestures |
| **D** | <img src="images/matrix/programs/D.png" alt="D matrix display illustration" width="104"> | Challenge mode | Reversed directions with thumb/index buttons |
| **E** | <img src="images/matrix/programs/E.png" alt="E matrix display illustration" width="104"> | Defender II | Ship movement, fire, smart bomb, evasive movement |
| **F** | <img src="images/matrix/programs/F.png" alt="F matrix display illustration" width="104"> | Sesame Street 1-2-3 | Open-hand Yes and closed-hand No |
| **G** | <img src="images/matrix/programs/G.png" alt="G matrix display illustration" width="104"> | Gun Smoke | Walk by position; combine index curl and a forward push to fire |
| **H** | <img src="images/matrix/programs/H.png" alt="H matrix display illustration" width="104"> | Training / general play | Familiar controls with pulsed buttons |
| **I** | <img src="images/matrix/programs/I.png" alt="I matrix display illustration" width="104"> | Knight Rider / driving | Wrist steering, throttle, brake, and turbo |

<!-- PAGEBREAK -->

## Program cards A–I

### A - Pinball rig

| Profile | See it |
| --- | --- |
| `program_a` | <img src="images/matrix/A.jpg" alt="A matrix display" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Right flipper / A |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Left flipper / Up |
| Roll the wrist left or right | <img src="images/gestures/actions/wrist-roll.png" alt="Rotate the wrist" width="96"> | Tilt / B |
| Pull the hand away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull the hand away from the camera" width="72"> | Toggle combined-flipper behaviour |

Use this profile for pinball tables and games that benefit from two independent
finger actions.

### B - Joust rig

| Profile | See it |
| --- | --- |
| `program_b` | <img src="images/matrix/programs/B.png" alt="B matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Move the hand left or right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move the whole hand left or right" width="96"> | Pulsed steering left or right |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | B button; see the [Joust play card](GAMEPLAY_GUIDE.md#joust) for its in-game use |
| Curl the index or middle finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger" width="72"> | Pulsed flap input |

Use this profile for Joust and any game where rhythmic, repeated presses matter.

### C - Gyruss rig

| Profile | See it |
| --- | --- |
| `program_c` | <img src="images/matrix/programs/C.png" alt="C matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Roll the wrist left or right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Rotate counter-clockwise or clockwise |
| Keep the index finger straight | <img src="images/gestures/actions/keep-index-straight.png" alt="Keep the index finger straight" width="72"> | Continuous fire |
| Pull the hand away from the camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull the hand away from the camera" width="72"> | Launch a bomb |

Use this profile for circular shooters and games with rotation plus rapid fire.

### D - Mirror-world rig

| Profile | See it |
| --- | --- |
| `program_d` | <img src="images/matrix/programs/D.png" alt="D matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Move the hand left or right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move the whole hand left or right" width="96"> | Reversed right or left direction |
| Raise or lower the hand | <img src="images/gestures/actions/vertical-movement.png" alt="Raise or lower the whole hand" width="96"> | Reversed down or up direction |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | First action button |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Second action button |

Use this profile for deliberate chaos, party challenges, or accessibility
experiments that need inverted direction mappings.

### E - Defender rig

| Profile | See it |
| --- | --- |
| `program_e` | <img src="images/matrix/programs/E.png" alt="E matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="96"> | Move the ship |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Fire |
| Roll the wrist left or right | <img src="images/gestures/actions/wrist-roll.png" alt="Rotate the wrist" width="96"> | Smart bomb |
| Curl the ring finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger" width="72"> | Rapid horizontal movement |

Use this profile for Defender II and multi-action shooters.

### F - Yes / No rig

| Profile | See it |
| --- | --- |
| `program_f` | <img src="images/matrix/programs/F.png" alt="F matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Close every finger into a fist | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing all fingers" width="72"> | No |
| Move an open hand in any direction | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move an open hand in any direction" width="96"> | Yes |

Use this profile for Sesame Street 1-2-3 and simple choice-driven games.

### G - Gun Smoke rig

| Profile | See it |
| --- | --- |
| `program_g` | <img src="images/matrix/programs/G.png" alt="G matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="96"> | Walk using horizontal and vertical hand movement |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Fire |
| Roll the wrist | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Add left or right movement |
| Curl the thumb and ring finger | <img src="images/gestures/actions/menu-guard.png" alt="Menu guard with thumb and ring finger curled" width="96"> | Suppress all ordinary controller output |

A forward push sends B. Combine it with index curl (A) to send A+B.

Use this profile for Gun Smoke and shooters with movement plus directional fire.

### H - Training rig

| Profile | See it |
| --- | --- |
| `program_h` | <img src="images/matrix/programs/H.png" alt="H matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Move the whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="96"> | Conventional directions |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Pulsed A |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Pulsed B |
| Return the hand to center | <img src="images/gestures/actions/whole-hand-movement.png" alt="Return the whole hand to center" width="96"> | Release directional input |

Use this profile for learning the system or giving an unmapped game a sensible
general-purpose starting point.

### I - Driving rig

| Profile | See it |
| --- | --- |
| `program_i` | <img src="images/matrix/programs/I.png" alt="I matrix display illustration" width="104"> |

| Gesture | See it | Controller result |
| --- | --- | --- |
| Roll the wrist left or right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Steer |
| Curl the index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Throttle |
| Lower the hand | <img src="images/gestures/v2/move-down.png" alt="Lower the whole hand" width="72"> | Brake |
| Push the hand toward the camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push the hand toward the camera" width="72"> | Turbo |
| Curl the thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Auxiliary action |

Use this profile for Knight Rider and driving games that need steering, speed, and
one extra action.

<!-- PAGEBREAK -->

## Bad Street Brawler

| Profile | See it |
| --- | --- |
| `bad_street_brawler` | <img src="images/matrix/BS.jpg" alt="BS matrix display" width="104"> |

**Your mission:** Guide Duke Davis through each stage, discover that stage's
three fighting moves at the practice bag, and clear the street before time or
vitality runs out.

| Do this | See it | Duke does this |
| --- | --- | --- |
| Move hand left / right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move the whole hand left or right" width="96"> | Walk left / right |
| Raise / lower hand | <img src="images/gestures/actions/vertical-movement.png" alt="Raise or lower the whole hand" width="96"> | Jump / crouch |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Pulsed B move |
| Curl middle finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger" width="72"> | A+B force move |
| Roll wrist left / right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | A plus that direction |
| Push toward camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push the hand toward the camera" width="72"> | Glove Zap |

**Play smart:** The available force moves change with each stage. Test the
thumb curl, middle-finger curl, and wrist rolls on the punching bag before
leaving practice. Push toward the camera to trigger Glove Zap, then return to
your starting distance before another attempt. The game controls its
once-per-round availability. If Zap does not work, check the
[game-specific setup](CONFIGURATION_REFERENCE.md#bad-street-brawler-glove-zap).

**First round:**

1. At the practice bag, try a thumb curl, a middle-finger curl, and a wrist roll separately.
2. Notice which move each gesture produces in this stage.
3. Enter the street and use one familiar move before adding combinations.

<!-- PAGEBREAK -->

## Super Glove Ball

| Profile | See it |
| --- | --- |
| `super_glove_ball` | <img src="images/matrix/GB.jpg" alt="GB matrix display" width="104"> |

**Your mission:** Control the Robo-Glove, keep the energy ball in play, break a
complete wall of tiles, and follow the revealed arrows through the maze.

**Nestopia (VirtualGlove)** means the custom `lr-nestopia-powerglove` core.
Use the controls below for the emulator that actually starts; FCEUmm is the
fallback. The RetroPie launch hook reports that running core automatically.
Only Super Glove Ball running in `lr-nestopia-powerglove` uses native input.
Starting the same ROM in FCEUmm—or in any other or unknown core—keeps joystick
output active for the whole session. The V sign sends Start in both modes.

| Do this | See it | Controller result |
| --- | --- | --- |
| Move whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in eight directions" width="96"> | FCEUmm: eight-direction digital steering. Nestopia (VirtualGlove): continuous hand positioning. |
| Curl index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | FCEUmm: A, move the glove into the room. |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | FCEUmm: B, punch, grab, or launch a new ball. |
| Open hand | <img src="images/gestures/actions/show-your-hand.png" alt="Open hand" width="72"> | Nestopia (VirtualGlove): release or throw a held ball. |
| Close hand | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing into a fist" width="72"> | Nestopia (VirtualGlove): grab or catch the ball. |
| Point index; curl middle, ring, and pinky | <img src="images/gestures/actions/keep-index-straight.png" alt="Point with the index finger while the other fingers are curled" width="72"> | Nestopia (VirtualGlove): fire a Robo-Bullet. |
| Close hand and push forward | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing into a fist" width="60"> <img src="images/gestures/v2/push-closed-fist.png" alt="Push a closed fist toward the camera" width="60"> | Nestopia (VirtualGlove): Power Punch. |

**Play smart:** Pick one wall and finish it, then follow the revealed arrow.
With FCEUmm, use Select to take the exit. Native gameplay has been completed
without Select; although the core can transmit its native button bit, no required
in-game action has been identified for it. **Latest coordinate** is the native
movement default. It follows each newest valid palm point directly
during continuous tracking and waits one fresh result only for a contradictory
or unusually distant non-forward reacquisition. Continuous native movement is
playable and has been
substantially tightened, although synchronized physical latency measurement is
still pending. The
[native compatibility record](super-glove-ball-native.md) contains the test
evidence and details about additional packet fields.

**First round:**

1. Move the Robo-Glove across the room with small hand movements.
2. With **Nestopia (VirtualGlove)**, practise closing to grab and opening to release. Try index-point fire and a fist-plus-forward Power Punch separately.
3. With **FCEUmm**, try the index-curl A action and thumb-curl B action separately.

<!-- PAGEBREAK -->

## Joust

| Profile | See it |
| --- | --- |
| `program_b` | <img src="images/matrix/programs/B.png" alt="B matrix display illustration" width="104"> |

**Your mission:** Ride the ostrich, strike enemy riders from above, collect
their eggs before they hatch, and stay clear of the lava.

| Do this | See it | Result |
| --- | --- | --- |
| Move hand left / right | <img src="images/gestures/actions/horizontal-movement.png" alt="Move the whole hand left or right" width="96"> | Pulsed steering left / right |
| Curl index or middle finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger" width="72"> | Pulsed A: steady flap |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | B: faster flap |
| Hold thumbs-up | <img src="images/gestures/v2/thumbs-up.png" alt="Hold a thumbs-up" width="72"> | Select game mode |

**Play smart:** Height wins jousts. Use the faster thumb flap to climb, then the
pulsed finger flap to hold position. Sweep up eggs quickly; every ignored egg is
an enemy preparing a return engagement.

**First round:**

1. Curl your index finger to practise a steady flap.
2. Move left and right while keeping your height.
3. Approach one rider from above, then collect the egg.

<!-- PAGEBREAK -->

## Gyruss

| Profile | See it |
| --- | --- |
| `program_c` | <img src="images/matrix/programs/C.png" alt="C matrix display illustration" width="104"> |

**Your mission:** Circle the tunnel, destroy incoming formations, survive the
warp zones, and fight from planet to planet toward the Sun.

| Do this | See it | Result |
| --- | --- | --- |
| Roll wrist left / right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Orbit counter-clockwise / clockwise |
| Keep index finger straight | <img src="images/gestures/actions/keep-index-straight.png" alt="Keep the index finger straight" width="72"> | Continuous A fire |
| Pull hand away from camera | <img src="images/gestures/v2/pull-away-from-camera.png" alt="Pull the hand away from the camera" width="72"> | B bomb |
| Hold thumbs-up | <img src="images/gestures/v2/thumbs-up.png" alt="Hold a thumbs-up" width="72"> | Select control mode |

**Before launching:** Choose **Attack Control B** at the title screen. This
profile expects left/right rotation rather than eight-direction movement.

**First round:**

1. Select Attack Control B at the title screen.
2. Keep your index straight and practise small wrist rolls in both directions.
3. Clear one formation before trying the pull-back bomb.

<!-- PAGEBREAK -->

## Defender II

| Profile | See it |
| --- | --- |
| `program_e` | <img src="images/matrix/programs/E.png" alt="E matrix display illustration" width="104"> |

**Your mission:** Patrol the planet, destroy alien raiders, and rescue the
humanoids before abductors carry them away and turn them into mutants.

| Do this | See it | Result |
| --- | --- | --- |
| Move whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="96"> | Fly up, down, left, or right |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | A: fire |
| Roll wrist either way | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist in either direction" width="96"> | B: smart bomb |
| Curl ring finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger" width="72"> | Rapid left/right evasive thrash |

**Play smart:** Watch the scanner as much as the ship. Intercept abductors early;
if one lifts a humanoid, shoot the alien and catch the falling person. Wrist
rolls trigger the smart-bomb action, so make them deliberate.

**First round:**

1. Fly a short circuit with your wrist level.
2. Curl your thumb to fire while moving.
3. Track one abductor on the scanner; save deliberate wrist rolls for smart bombs.

<!-- PAGEBREAK -->

## Sesame Street 1-2-3

The same game may appear in your library as **Sesame Street 123**.

| Profile | See it |
| --- | --- |
| `program_f` | <img src="images/matrix/programs/F.png" alt="F matrix display illustration" width="104"> |

**Your mission:** Play the counting activities by giving the game a simple,
physical Yes or No answer.

| Do this | See it | Result |
| --- | --- | --- |
| Move an open hand in any direction | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move an open hand in any direction" width="96"> | A: Yes |
| Close every finger into a fist | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove closing all fingers" width="72"> | B: No |

**Play smart:** Directional output is intentionally disabled in this profile.
Make the open-hand answer broad and obvious; make the fist complete. Return to a
relaxed open hand between questions so one answer does not run into the next.

**First round:**

1. Count the objects before making a gesture.
2. Move an open hand from the resting position for Yes, or close all fingers for No.
3. Return to a relaxed hand at the centre before the next question.

<!-- PAGEBREAK -->

## Gun Smoke

| Profile | See it |
| --- | --- |
| `program_g` | <img src="images/matrix/programs/G.png" alt="G matrix display illustration" width="104"> |

**Your mission:** Walk the scrolling frontier, defeat the bandits, find or buy
each wanted poster, and collect the bounty by beating the stage boss.

| Do this | See it | Result |
| --- | --- | --- |
| Move whole hand | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="96"> | Walk in that direction |
| Curl index finger | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling the index finger" width="72"> | A: shoot diagonally right |
| Push toward camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push the hand toward the camera" width="72"> | B: shoot diagonally left |
| Curl index while pushing | <img src="images/gestures/actions/index-push-combination.png" alt="One six-digit glove curling a finger beside a glove pushing toward the camera" width="96"> | A+B: shoot straight ahead |
| Curl thumb and ring finger | <img src="images/gestures/actions/menu-guard.png" alt="Menu guard with thumb and ring finger curled" width="96"> | Suppress D-pad, A/B, Start, and Select |

**Play smart:** A stage keeps looping until you obtain its wanted poster. Keep
your palm level while walking; wrist roll can add a left/right movement command.
Use index-plus-push when you need the straight-ahead shot.

**First round:**

1. Try an index curl for the right shot and a forward push for the left shot.
2. Combine them to fire straight ahead.
3. Walk while firing, then look for the wanted poster.

<!-- PAGEBREAK -->

## Knight Rider

| Profile | See it |
| --- | --- |
| `program_i` | <img src="images/matrix/programs/I.png" alt="I matrix display illustration" width="104"> |

**Your mission:** Drive KITT from city to city, avoid roadside hazards, destroy
the criminals ahead, and reach each destination before the timer expires.

| Do this | See it | Result |
| --- | --- | --- |
| Roll wrist left / right | <img src="images/gestures/actions/wrist-roll.png" alt="Roll the wrist left or right" width="96"> | Steer left / right |
| Curl index finger | <img src="images/gestures/v2/curl-index.png" alt="Curl the index finger" width="72"> | Accelerate |
| Lower hand | <img src="images/gestures/v2/move-down.png" alt="Lower the whole hand" width="72"> | Brake |
| Push toward camera | <img src="images/gestures/v2/push-toward-camera.png" alt="Push the hand toward the camera" width="72"> | Accelerate plus turbo boost |
| Curl thumb | <img src="images/gestures/v2/curl-thumb.png" alt="Curl the thumb" width="72"> | Fire weapons |

**Play smart:** Keep the wrist near center on straight roads; large steering
rolls are for real turns. Keep your index finger curled for normal speed and reserve the
forward push for a clean burst when the road opens.

**First round:**

1. Curl your index finger to accelerate and make small wrist rolls to steer.
2. Lower your hand to practise braking.
3. Use a forward push for turbo only when the road ahead is clear.

<!-- PAGEBREAK -->

## Make the controls fit your hand

### Choose a player and save your setup

Choose a player in **Active player** before practising or tuning. Each player keeps
separate sensitivity, lesson progress, and a saved centre. Selecting a player
loads all three automatically and pauses controller output. Use **Center hand**
for players without a saved centre or after moving the camera or changing playing position.

Use **Setup → Players → Players and hand-setup backups → Back up hand setup** to save the player's
name, center-box size, personal and complete gesture sensitivity, software identity, and calibration.
During restore, choose whether to keep the complete saved sensitivity, including
the defaults used when the backup was made, or just personal adjustments. Reuse
calibration only with the same camera and playing position; otherwise set a fresh
centre. Backups do not include credentials or Academy progress. New exports use
the `virtualglove-hand-setup` format at version 4. Older backup formats are
rejected without changing the selected player.

Choose each player in turn and select **Back up hand setup** to download a
separate file named for that player, such as
`alex-virtualglove-hand-setup.json`. Your browser saves it on the computer, phone,
or tablet you are using, usually in **Downloads** or the folder you choose. To restore, select
the player you want to update, choose **Restore hand setup**, and pick that
player's saved file from your device. Review it before confirming; restore
updates the selected player, rather than adding a new one.

![Player selection and complete hand-setup backups](images/player-settings.png)

### Tune a difficult gesture

Tuning is optional. In **Glove Academy**, switch on **Tune gestures**. Pixel Pal
helps with a new hand setup, a difficult or accidental gesture, or movement that
feels off-centre. This adjusts recognition thresholds, not a personal camera
model. It does not change the game's button assignments.

1. Choose what you want to improve and follow the framing advice.
2. When your whole hand is tracked clearly, select **I'm ready**.
3. Follow the countdown and prompts. Finger poses use open hand, performed pose, then open hand again. Movement uses your starting position, the motion, then a return. Forward and backward movements are repeated three times.
4. Test the result with two clean activations and releases, then hold neutral for three seconds. Save when the check passes, or retry the indicated pose.

![Tune mode with Pixel Pal guiding the personalization choices](images/tune-page.png)

Cabinet output stays paused during practice and tuning. The live camera area is
excluded from these screenshots for privacy. Tune one difficult gesture without
repeating the whole hand setup. Pixel Pal may suggest better framing or lighting;
it does not change camera exposure automatically.

Use the separate **Movement reach** section when native Super Glove Ball needs
more or less physical travel. Left, right, up, and down are normalized distances
from the saved center; smaller values reach the corresponding screen edge sooner.
The summary shows the tracking area's width, height, and aspect ratio. Saving
changes only those four reach spans. **Restore full camera field** returns to the
camera-boundary mapping without changing the center or gesture sensitivity.

Setup's advanced camera settings offer Automatic, 30 fps, and 60 fps. Automatic
prefers the tested 30-fps path and falls back safely to a camera-supported rate;
the active rate is shown while tracking runs. Leave it on Automatic unless a
specific camera comparison is needed.

Exposure is also Automatic by default. If a compatible Linux UVC camera looks
too dark or loses the hand during fast movement, Setup offers exposure controls.
Direct V4L2 remains an engineering comparison with Manual exposure and gain.
The page shows whether manual control was supported
and which values were actually applied. The project's Kiyo Pro tested well at
exposure `78` and gain `96`, but lighting and camera models differ. Manual mode
returns the camera to automatic exposure when tracking closes.

Leave **Advanced thresholds and diagnostics** closed unless you need numerical
controls or a diagnostic run. The [Configuration Reference](CONFIGURATION_REFERENCE.md)
explains the threshold checks and targeted restore options.

### Check the result in a game

Return to Dashboard, select **Start controller**, and try the same gesture in a
short game session. Check that it activates reliably and releases when you return
to rest. If another gesture activates accidentally, stop delivery and revisit
that pose in Glove Academy. Saved sensitivity is shared across your selected
player's games; each game profile still decides the resulting actions.

## Understand the matrix display

The matrix shows the active game or practice mode. Each play card includes its
game display; the images below identify Academy and tuning.

| Mode | See it | Controller output |
| --- | --- | --- |
| Glove Academy lessons | <img src="images/matrix/L.jpg" alt="L matrix display" width="104"> | Paused while you practise |
| Tune gestures | <img src="images/matrix/T.jpg" alt="T matrix display" width="104"> | Paused while you record or preview thresholds |

For the idle display, choose **Setup → Matrix attract mode**: **On**, **Dim**, or
**Off** with faint connection pixels. This affects only the idle animation, not
game displays, Academy, tuning, or gesture recognition. The setting saves without
restarting tracking. See the [Matrix display guide](MATRIX_GUIDE.md) for connection
pixels, startup animations, and the full display reference.

<!-- PAGEBREAK -->

## How VirtualGlove selects a program

Choose the current profile on Dashboard; choose the saved startup profile on
Setup. Automatic selection matches the complete ROM filename, including its
extension but excluding its folder path, against `/etc/virtualglove/games.json`
on RetroPie. Matching ignores letter case.

The launch hook sends an authenticated profile request. The VirtualGlove Controller releases held
controls, changes the mapping, reuses the saved calibration, and acknowledges
the new profile on its blue matrix. If no valid calibration is saved, it collects
an initial reference while you hold your open hand still in a comfortable
resting position. It uses 24 geometrically valid observations; repeating
the same center, distance, and wrist pose produces a similar rather than
bit-for-bit identical reference.

```json
{
  "games": {
    "Joust (USA).zip": "program_b",
    "Gyruss (USA).nes": "program_c",
    "Gun.Smoke (USA).7z": "program_g"
  }
}
```

Merge entries into the existing `games` object; do not replace other registered
games. The matrix displays `1` through `14` or `A` through `I` for those
profiles. When an unknown game starts, the launch hook turns gesture control off so
the previous game's mapping does not remain active.


<!-- PAGEBREAK -->

## Take VirtualGlove off-script

You can use the included profiles with games beyond Mattel's indexed titles and
the dedicated play cards in this guide. Programs 1–13 and A–I send ordinary NES
controller inputs, so try matching their gestures to games with similar
controls. Programs 2, 11, 13, A, D, and H have no default ROM assignment and
are useful starting points for these experiments. Program 14 is the deliberate
camera-and-output-off choice rather than a general gesture mapping.

### Start with 2, 11, 13, A, D, and H

| Program | See it | Try it with | Know before playing |
| --- | --- | --- | --- |
| **2 - Centering coach** | <img src="images/gestures/v2/find-neutral.png" alt="Relaxed hand at the saved center" width="104"> | Maze, platform, and precision-movement games where a clear neutral position helps | It uses Program 1's D-pad and A/B gestures, while Dashboard adds live **Centered** / **Return to centre** feedback. |
| **11 - Fast turn** | <img src="images/gestures/actions/close-all-fingers.png" alt="Six-digit glove curling the last three fingers for the fast-turn action" width="104"> | Arena action and shooters that benefit from a repeated left/right turn while firing | Hand position and thumb/index curls follow Program 1. Curling the last three fingers alternates Left/Right and fires B until released. |
| **13 - Finger buttons** | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling the index finger for a gesture action button" width="104"> | Games where you want gesture A/B while keeping movement and menus on the physical Player 1 controller | Thumb and index curls provide A and B. Camera movement sends no D-pad, so the merged physical controller remains in charge of direction. |
| **A - Pinball** | <img src="images/gestures/actions/wrist-roll.png" alt="Rotate the wrist for the pinball tilt action" width="176"> | Pinball and games driven by two independent actions | Index curl is A, thumb curl is Up, wrist tilt is B, and pulling back toggles combined flippers. Ordinary directional movement is disabled. |
| **D - Mirror world** | <img src="images/gestures/actions/whole-hand-movement.png" alt="Move the whole hand in four directions" width="176"> | A game you already know well, a party challenge, or an inverted-direction accessibility experiment | Every direction is reversed. Thumb and index provide A and B. Expect your muscle memory to complain loudly. |
| **H - General play** | <img src="images/gestures/actions/finger-curl.png" alt="Six-digit glove curling a finger for a general-purpose action button" width="176"> | Two-button platform, maze, puzzle, and action games | Hand movement supplies the D-pad. Thumb pulses A and index pulses B, so games that require a long held button may be a poor fit. |

Try Program H for general play, Program 2 when neutral-position feedback would
help, or Program 13 when you want the physical controller to handle movement.
Program 11 supplies a sustained fast turn, Program A covers pinball controls,
and Program D turns a familiar game into a new coordination challenge without
changing the ROM or emulator.

### Try a combination

1. Launch the NES or Famicom game normally. An unregistered game safely turns gesture output off instead of inheriting the previous game's controls.
2. Open the VirtualGlove Controller **Dashboard** and choose **2: Centering coach**, **11: Fast turn**, **13: Finger buttons**, **A: Pinball**, **D: Challenge**, **H: General**, or another Program 1–14 or A–I profile from **Active profile**.
3. Use **Center hand** if your resting hand position produces unwanted movement or your physical setup has changed. Hold a relaxed open hand still at your intended centre and distance until calibration finishes, then select **Start controller** and return to the game.
4. Test movement, both action gestures, Start, and Select before committing to a long session. Stop the controller immediately if a gesture remains active.

The selection is temporary. Starting or ending a game sends a new command
that changes the profile or turns gestures off.

### Keep a discovery

Open **Setup → Games** and map the game's exact ROM filename to the profile
that worked. Include its `.nes`, `.zip`, or `.7z` extension, validate, and save.
Restart the game to use the new mapping. Automatic selection is currently limited
to NES and Famicom; other systems turn gesture control off until their mappings
and launch behaviour are validated.

![Games mappings in the lower section of Setup](images/games-section.png)

Do not stop at A, D, and H. Try B when rhythmic button pulses suit the action,
C when wrist rotation can replace horizontal movement, F for simple Yes/No
choices, or I when steering and throttle are the heart of the game. Match the
profile to the game's mechanics, not to the title printed on the cartridge.

> **GLOVE LAB RULE**  A strange pairing that is controllable, repeatable, and
> fun is a successful experiment. Record the exact ROM filename and profile so
> somebody else can reproduce it.

For registry validation and manual profile commands, see the
[Configuration Reference](CONFIGURATION_REFERENCE.md).

<!-- PAGEBREAK -->

## Sources, artwork, and fair play

The profile descriptions are checked against the project's implemented gesture
engine and tests. Game objectives and original control intent were summarized
from the following historical instruction sources:

- Mattel, *Power Glove Instruction Manual* (complete manual; Program 4 and the
  official game index), supplied for this release's documentation review
- Mattel, *Power Glove Program Guide* (1988 US; program illustrations and the
  1943 workflow), supplied for this release's documentation review
- [Mattel Power Glove instructions and Programs A-I](https://home.hiwaay.net/~lkseitz/cvg/power_glove.shtml)
- [Bad Street Brawler NES instruction transcription](https://www.world-of-nintendo.com/manuals/nes/bad_street_brawler.shtml)
- [Super Glove Ball NES instruction manual](https://www.digitpress.com/library/manuals/nes/Super%20Glove%20Ball.pdf)
- [Joust NES instruction transcription](https://www.world-of-nintendo.com/manuals/nes/joust.shtml)
- [Gyruss NES instruction transcription](https://www.world-of-nintendo.com/manuals/nes/gyruss.shtml)
- [Defender II NES instruction transcription](https://www.world-of-nintendo.com/manuals/nes/defender_2.shtml)
- [Gun Smoke NES gameplay reference](https://strategywiki.org/wiki/Gun.Smoke_%28NES%29/Gameplay)
- [Knight Rider NES instruction manual](https://www.retrogames.cz/manualy/NES/Knight_Rider_-_NES_-_Manual.pdf)

The gesture drawings are original VirtualGlove project illustrations made
for this guide. They deliberately avoid game screenshots, box art, characters,
and publisher logos.

VirtualGlove is an independent MIT-licensed hobbyist project by Iain
Bennett. Nintendo, NES, Power Glove, and all game titles and marks belong to
their respective owners. No ROM images or original game artwork are distributed.

<!-- PAGEBREAK -->

## Pixel Pal's Extra-Digit Hunt answer

<img src="images/gestures/v2/pixel-pal.png" alt="Pixel Pal reveals the Extra-Digit Hunt answer" width="180">

**Pixel Pal's answer: 28 six-digit hands.**

One appears in the opening Rock, Paper, Scissors table. Ten appear in the
numbered Program cards: Programs 1, 2, 4, 6, 7, 9, 10, and 11, with Program 12
appearing twice. Two more appear in the Program 11 and Program 13 off-script
cards. The remaining fifteen appear in the shared gesture reference, dedicated
game cards, Programs B, E, and F, and the Program H off-script card. Every
appearance counts, even when the same artwork returns.
