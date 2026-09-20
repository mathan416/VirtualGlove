# Build Your Own: Parts, Cost, and Difficulty

VirtualGlove lets you use a camera-recognized hand to control games through
RetroArch on RetroPie, Recalbox, Batocera, or LaunchBox. The **VirtualGlove
Controller (Arduino UNO Q)** handles the camera, recognition, and website. The
selected console runs the game. You do not need an original
Power Glove or electronics attached to your hand.

This is a hobby project with working gameplay, not a finished consumer accessory.
Native Super Glove Ball is playable, but noticeable movement latency remains.
Choose it if you enjoy experimenting and can work through a little Linux setup.

## What you need

| Part | What to look for | Evidence and limits |
| --- | --- | --- |
| VirtualGlove Controller | Arduino UNO Q, provisioned with Arduino App Lab | This is the project's supported Controller platform. Other Arduino UNO boards are not substitutes. This guide does not establish equivalent performance across RAM variants. |
| USB camera | A Linux-compatible UVC webcam with a stable mount | Razer Kiyo Pro is the camera used in the recorded cabinet tests. Other UVC cameras need validation; sharing a USB connector does not guarantee the same formats or timing. |
| Powered USB hub or dock | USB data connectivity for the camera and compatible Controller power arrangement | A powered hub is part of the documented setup. Ethernet through a USB dock is used on the project cabinet; a specific dock model has not been recorded as a universal recommendation. |
| Power supplies and data cables | Supplies appropriate to the Controller, dock, and console | Check power delivery and upstream data roles before buying. A charge-only cable will not connect a camera. |
| Supported console | Working RetroPie, Recalbox 10.x, Batocera 38+, or 64-bit Windows with LaunchBox and 64-bit RetroArch | Verify ordinary gamepad play first. Native Super Glove Ball additionally needs a matching target-built Nestopia (VirtualGlove) core. |
| Conventional gamepad | A working USB or Bluetooth controller for the cabinet | Keep it available for RetroArch setup, Libretro setup, EmulationStation setup, menus, and comparison tests. |
| Browser and local network | Computer, phone, or tablet; a LAN shared by both devices | The browser controls setup. It does not perform recognition. Wi-Fi or supported USB Ethernet can connect the Controller. |
| Optional extras | Camera stand, front lighting, cable ties, plain glove | Start with a bare hand. Glove colour is a diagnostic label, not a different recognition model. |

Arduino lists a USB-C port supporting host/device roles and a 5 V, up-to-3 A
USB-C supply specification for the board. Follow the manufacturer's power and
hub guidance; the camera and dock add their own requirements. See the
[official UNO Q specifications](https://store.arduino.cc/products/uno-q) before
choosing the power arrangement. The recorded camera model is documented by
[Razer](https://mysupport.razer.com/app/answers/detail/a_id/4104/).

## Budget before you buy

These are **planning allowances**, not vendor quotations or a promise that a
particular accessory will work. Amounts appear in Canadian dollars (CA$), euros
(€), British pounds (£), and US dollars (US$), in that order. They exclude
shipping, regional tax differences, games, and a display. Check local prices
and returns policies.

Conversions use the [European Central Bank reference rates for September 4, 2026](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html):
CA$1.6038 / €1 / £0.85898 / US$1.1622. Planning figures are rounded to the nearest
five currency units; totals are converted and rounded independently. These are
currency equivalents of the same allowance, not researched local retail prices.

| Item | CA$ | € | £ | US$ |
| --- | --- | --- | --- | --- |
| Controller board | CA$95–135 | €60–85 | £50–75 | US$70–100 |
| UVC camera | CA$65–240 | €40–150 | £35–130 | US$45–175 |
| Powered hub/dock | CA$50–110 | €30–70 | £25–60 | US$35–80 |
| Controller/dock power | CA$30–55 | €20–35 | £15–30 | US$25–40 |
| Cables and camera mount | CA$25–55 | €15–35 | £15–30 | US$15–40 |
| Console computer and storage, if needed | CA$160–290 | €100–180 | £85–155 | US$115–210 |
| Gamepad, if needed | CA$25–55 | €15–35 | £15–30 | US$15–40 |

Reuse a working cabinet, gamepad, camera, cables, and mount where possible. Check
hub data/power compatibility, and avoid budgeting twice for included supplies.

| Budget scenario | CA$ | € | £ | US$ |
| --- | --- | --- | --- | --- |
| Existing cabinet: first five items | CA$265–600 | €165–375 | £140–320 | US$190–435 |
| Example mid-range setup | CA$330 | €205 | £175 | US$240 |
| Additional console kit and gamepad | CA$185–345 | €115–215 | £100–185 | US$135–250 |

The example uses a board, camera, hub, power supply, and cables/mount. These
estimates are not a complete cabinet build cost. Expensive cameras, displays,
and enclosure work can raise the total substantially.

When printing an enclosure, use the design-specific UNO Q Case, Controller Dock
V1, or Controller Dock V2 bundle linked from the
[Controller Enclosure Guide](ENCLOSURE_GUIDE.md). Each archive includes only the
matching structural pieces, lid-branding choices, fit coupons, finishing part,
and parametric source. Individual STL and 3MF links remain available.

As a dated retail reference, Arduino's EU store showed the UNO Q 2GB at
**CA$96.07 / €59.90 / £51.45 / US$69.62** on September 6, 2026, including EU VAT.
Only the euro amount is the store quotation; the other amounts are conversions
using the rates above, not Canadian, UK, or US offers.
[Arduino store](https://store.arduino.cc/products/uno-q)

## Difficulty and time

No soldering or glove construction is required by the documented setup. You
should be comfortable opening a terminal, copying commands carefully, finding
network addresses, and checking a service when a step fails.

Allow an afternoon for a first attempt with provisioned hardware and a working
supported console. That is a planning estimate, not a measured installation time.
Downloads, board provisioning, a native-core compile, unfamiliar networking, or
camera trouble can extend it. Enclosure building and preparing the console from
scratch are separate tasks.

The easiest starting point is local **Play → Rock Paper Scissors** and
**Glove Academy**. Neither requires a paired console, so they let you
verify the camera and learn the gestures before debugging game delivery.

## Assemble and test in stages

1. Make sure the selected console already plays an NES game with its conventional controller.
2. Provision the Controller using Arduino's supported App Lab workflow. Arrange its power, powered hub/dock, and camera according to the hardware guidance.
3. Put both machines on the same reachable LAN. A USB Ethernet link can be used alongside Wi-Fi; the addresses may differ. Record their hostnames and current addresses.
4. Follow the [Installation Guide](INSTALL_README.md) for matching software on both machines. Use its maintained commands rather than copying an old release command from a forum post. Recalbox/Batocera also ask which configured pad is physical Player 1; identify it before installation when several controllers are attached.
5. Open Glove Academy, choose your player, and verify that the whole hand stays visible. Work through the sixteen lessons and save your centre.
6. In Setup, select and save the console platform and address, then pair. Every method requires the Controller's matrix PIN and certificate-ID check. LaunchBox uses one-time-code pairing only; the Linux consoles may also use SSH password pairing.
7. Start with a standard game mapping. Try native Super Glove Ball after ordinary delivery works, using the [Gameplay Guide](GAMEPLAY_GUIDE.md).
8. Export each player's hand setup to your browser device and keep a named backup. See [where the files live](CONFIGURATION_REFERENCE.md#where-player-settings-and-backup-files-live).

Keep the camera and resting position fixed during testing. A green Networking
indicator means a physical link is up; the two console checks establish separate
service and authentication results. None proves the game received an input.

## Before calling the build finished

Check clean starts, a stable hand view, intentional Start/Select gestures, ordinary
gamepad fallback, and a short game session. A Glove Master award demonstrates
lesson completion, not measured cabinet latency. Use the
[symptom guide](TROUBLESHOOTING.md) when a stage fails and change one thing at a time.

To help another hobbyist reproduce your result, record the board variant,
camera and dock model, OS/core versions, display settings, lighting, and what
you actually tested. Keep pairing tokens and private camera footage out of
public reports. The project distributes no ROM images.
