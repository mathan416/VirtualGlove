# VirtualGlove Enclosure Assembly Quick Reference

This is the workbench companion to the
[Controller Enclosure Guide](ENCLOSURE_GUIDE.md). The downloadable PDF is a
single-page, diagram-first assembly sheet designed to stay beside the printer
or parts tray. This page adds the short explanations that are useful while
building without repeating the full printing guide.

## Start here

1. Disconnect the UNO Q and hub from power.
2. Confirm that the printed parts sit flat and that every vent is open.
3. Test the USB-C plug in the fit coupon before mounting electronics.
4. If building the Controller Dock, test the hub in its fit coupon too.

Do not force a board, cable, insert, or lid. A part that needs force is telling
you that its fit or alignment needs attention.

## Choose your assembly path

| Build | Use it when | Printed structural parts | Hub location |
| --- | --- | --- | --- |
| **UNO Q Case** | You want the smallest Controller enclosure | UNO Q base and lid | Outside the case |
| **Controller Dock** | The UNO Q and Arduino hub should move as one unit | Dock base and lid | Open service bay in the Dock |

Both builds use the same UNO Q mounting position, four board screws, four case
screws, four heat-set inserts, Matrix bezel, and optional hand/target emblem.

## Lay out the parts

Before heating an insert, arrange the complete build on the bench:

- Arduino UNO Q;
- Arduino USB-C Hub (8 in 1);
- the chosen printed base and lid;
- four M3 x 8 mm board screws;
- four M3 x 8-12 mm case screws;
- four M3 heat-set inserts;
- M3 driver and heat-set tool;
- Matrix bezel and optional emblem layers;
- four adhesive rubber feet.

The compact case still uses the hub; it simply leaves the hub outside the
printed enclosure.

## UNO Q Case

![Exploded assembly view of the UNO Q Case](../hardware/enclosures/previews/virtualglove-uno-case-exploded.png)

### 1. Fit the inserts

Place one insert over each corner boss. Heat it squarely and stop as soon as it
is flush with the boss. Let the plastic cool before testing a screw.

### 2. Mount the UNO Q

Set the board on its four standoffs with the USB-C socket facing the broad side
opening. Install the four board screws evenly. They should be snug, not tight
enough to flex the board.

### 3. Check the connection

Connect the hub through the USB-C opening. The plug must enter straight without
pressing sideways on the UNO Q socket. Disconnect it again before closing the
case.

### 4. Close and finish

Lower the lid without force, install the four case screws, then fit the Matrix
bezel and optional emblem. Add the rubber feet last so the bottom vents retain
air space.

## Controller Dock

![Exploded assembly view of the Controller Dock](../hardware/enclosures/previews/virtualglove-controller-dock-exploded.png)

### 1. Fit the inserts and mount the UNO Q

Install the four inserts as described above. Mount the UNO Q with its USB-C
socket facing the broad opening and fasten the board evenly to its standoffs.

### 2. Seat the hub

Place the Arduino hub in the open service bay with its usable ports facing
outward. It should sit securely without bowing the Dock or rattling. Use only a
thin foam or TPU strip if the fit needs quieting.

### 3. Route the captive cable

Guide the hub cable through its channel and connect it straight into the UNO Q.
Keep the cable in the channel, preserve a gentle bend, and confirm that it sits
below the lid line.

### 4. Close and finish

Lower the lid while watching the cable. Install the four case screws, Matrix
bezel, optional emblem, and rubber feet. The hub remains removable from its
open bay for service.

## Before power

Run a finger around the enclosure and confirm every item:

- the lid sits flat without being pulled down by its screws;
- no cable is trapped, sharply bent, or pressing on the UNO Q socket;
- the Matrix window and bezel are aligned;
- the UNO Q USB-C opening is clear;
- the Dock's hub ports face outward and remain reachable;
- all ventilation openings have clear air space;
- no loose screw or insert remains inside;
- the enclosure stands securely on all four feet.

Reconnect the hub, camera, power, and optional Ethernet only after this check.
During the first 30-minute camera-active test, make sure the enclosure remains
stable and that warm air can leave through the vents.

## If something does not fit

- **USB-C rubs or pulls sideways:** stop and reprint the fit coupon with an
  adjusted clearance.
- **Hub rocks in the Dock:** add a thin foam or TPU strip; do not wedge it
  against a port.
- **Lid will not sit flat:** remove it and inspect the board, cable routing, and
  insert height.
- **Screw will not start cleanly:** let the insert cool, then check that it is
  square. Do not use the screw to straighten a hot insert.

Use the [Controller Enclosure Guide](ENCLOSURE_GUIDE.md) for STL downloads,
printer settings, fit adjustments, side and rear views, branding, and OpenSCAD
customization.
