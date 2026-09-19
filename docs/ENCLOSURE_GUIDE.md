# VirtualGlove Controller Enclosure Guide

VirtualGlove now includes two printable homes for the Arduino UNO Q Controller.
Both were designed for an Anycubic Kobra 3, ordinary PLA, a 0.4 mm nozzle, and
the Arduino USB-C Hub (8 in 1).

The files are intentionally parametric. Print the small fit tests first, record
what changed, and adjust the clearances before committing to a long print.

## Choose your case

![UNO Q Case exterior](../hardware/enclosures/previews/virtualglove-uno-case-exterior.png)

### UNO Q Case

Choose the compact case when the Arduino hub will sit elsewhere in the arcade
panel. The case protects the UNO Q, exposes only its USB-C connection, keeps the
Matrix visible, and leaves airflow around the board.

- Outside size: approximately **90 × 76 × 27 mm** when assembled.
- Best for: a hidden controller, short cable runs, or the smallest possible box.
- The USB-C hub, camera cable, power cable, and optional Ethernet cable remain
  outside the enclosure.

![Controller Dock exterior](../hardware/enclosures/previews/virtualglove-controller-dock-exterior.png)

### Controller Dock

Choose the Dock when the UNO Q and Arduino hub should move and mount as one
unit. The hub sits in an open service bay, so its USB, USB-C power, and Ethernet
connections remain reachable.

- Outside size: approximately **148 × 104 × 31 mm** when assembled.
- Best for: a neat arcade-panel installation or a Controller given as a complete
  unit.
- The hub remains removable; it is not trapped inside a sealed hot box.

## What is included

The source and ready-to-print files are in `hardware/enclosures/`.

| Part | Purpose |
| --- | --- |
| UNO base and lid | Compact UNO Q enclosure |
| Dock base and lid | Combined UNO Q and hub enclosure |
| Matrix bezel | Cyan frame around the visible Matrix |
| Hand/target lid emblem | Small three-colour project mark for either enclosure |
| Full-logo layers | Optional dark, cyan, and red display plaque |
| Hand/target layers | Optional dark, cyan, and red emblem |
| USB-C coupon | Checks the UNO Q plug opening before a long print |
| Hub coupon | Checks the Arduino hub cradle before a long print |

The full-logo and hand/target pieces are printable adaptations of the project
artwork. They preserve the italic wordmark, hand, target, cyan linework, and red
accents while removing screen-only glow and details smaller than a dependable
0.4 mm nozzle can reproduce.

![Print-safe full logo and hand-target emblem](../hardware/enclosures/previews/virtualglove-printable-branding.png)

### Download the print files

From the Controller's local Help page, select any file below to download it.
The same files are kept in `hardware/enclosures/stl/` in the source tree.

**UNO Q Case**

- [UNO Q base](../hardware/enclosures/stl/virtualglove-uno-base.stl)
- [UNO Q lid](../hardware/enclosures/stl/virtualglove-uno-lid.stl)

**Controller Dock**

- [Dock base](../hardware/enclosures/stl/virtualglove-dock-base.stl)
- [Dock lid](../hardware/enclosures/stl/virtualglove-dock-lid.stl)

**Shared details and fit checks**

- [Matrix bezel](../hardware/enclosures/stl/virtualglove-matrix-bezel.stl)
- [USB-C fit coupon](../hardware/enclosures/stl/virtualglove-usb-c-fit-coupon.stl)
- [Hub fit coupon](../hardware/enclosures/stl/virtualglove-hub-fit-coupon.stl)

**Small hand/target lid emblem**

- [Dark backing](../hardware/enclosures/stl/virtualglove-lid-logo-backing.stl)
- [Cyan hand and target](../hardware/enclosures/stl/virtualglove-lid-logo-cyan.stl)
- [Red target beam](../hardware/enclosures/stl/virtualglove-lid-logo-red.stl)

**Optional full-logo plaque**

- [Dark backing](../hardware/enclosures/stl/virtualglove-full-logo-backing.stl)
- [Cyan hand and wordmark](../hardware/enclosures/stl/virtualglove-full-logo-cyan.stl)
- [Red target accents](../hardware/enclosures/stl/virtualglove-full-logo-red.stl)

**Optional larger hand/target emblem**

- [Dark backing](../hardware/enclosures/stl/virtualglove-target-badge-backing.stl)
- [Cyan hand and target](../hardware/enclosures/stl/virtualglove-target-badge-cyan.stl)
- [Red target beam](../hardware/enclosures/stl/virtualglove-target-badge-red.stl)

To change a dimension, download the
[parametric OpenSCAD source](../hardware/enclosures/virtualglove-controller.scad)
and the [STL export script](../hardware/enclosures/export-stl.sh).

## Before printing

You will need:

- an Arduino UNO Q;
- the Arduino USB-C Hub (8 in 1) for either design;
- four M3 × 8 mm screws for the board;
- four M3 × 8–12 mm screws for the case;
- four M3 heat-set inserts with an outside diameter near 4.0–4.2 mm;
- four adhesive rubber feet; and
- optional 1 mm foam or TPU strips beneath the hub.

The design follows Arduino's published **68.58 × 53.34 mm** UNO Q outline and
four mounting holes. The hub envelope is **119 × 27.8 × 16 mm** with a fixed
175 mm cable. Arduino does not publish every plug-body and overmould dimension,
so the coupons are part of the build process rather than an optional extra.

Reference drawings:

- [Arduino UNO Q datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-datasheet.pdf)
- [Arduino UNO Q STEP model](https://docs.arduino.cc/resources/models/ABX00162-step.zip)
- [Arduino USB-C Hub datasheet](https://docs.arduino.cc/resources/datasheets/TPX00241-datasheet.pdf)

## First check-in: print the coupons

Print these before the enclosure:

1. `virtualglove-usb-c-fit-coupon.stl`
2. `virtualglove-hub-fit-coupon.stl`

The USB-C plug should enter without scraping and should not have enough side
play to pull hard against the UNO Q socket. The hub should sit in its channel
without bowing the coupon or rattling loosely.

Record the printer, material, nozzle, slicer profile, and any dimensional change
you make. In `virtualglove-controller.scad`, `fit` controls ordinary mating
clearance and `hub_fit` controls the hub cradle. Do not scale the entire model
to fix one opening; change the relevant clearance instead.

## Kobra 3 PLA starting profile

- 0.4 mm nozzle
- 0.20 mm layer height
- four walls
- five top and bottom layers
- 20–25% gyroid infill
- supports off initially
- brim only if the base corners lift
- base and lid in the supplied orientation

The lid's visible face lies on the bed for a clean finish. PLA is suitable
inside a normal arcade cabinet. Do not leave the Controller in a hot car or
another high-temperature location, and never cover its ventilation slots.

## Printing the branding

The lid emblem is a compact version of the hand/target project mark. For the
closest match to the VirtualGlove artwork, use charcoal or black for the
backing, cyan for the hand and target corners, and red for the target beam. The
larger optional plaque combines the same mark with the full wordmark.

The colour layers are separate STL files. With one ACE Pro, assign each layer
its colour in the slicer and assemble them on the same plate, or print one colour
at a time and glue the layers to the backing. Separate accents avoid wasting
material on colour changes through an entire enclosure.

Use a small amount of thin double-sided adhesive or plastic-safe glue. Dry-fit
the pieces first; the detailed layers are intentionally shallow and should not
be forced.

## Assemble the UNO Q Case

1. Heat the four inserts into the corner bosses. Keep them square and stop when
   they are flush; excess heat can soften the boss.
2. Fasten the UNO Q to the four standoffs.
3. Connect the Arduino hub through the broad USB-C opening.
4. Dry-fit the lid and confirm the plug does not press on the socket.
5. Add the Matrix bezel and preferred badge.
6. Fasten the lid and add the rubber feet.

Only the UNO Q USB-C port is intentionally exposed. Do not force a thick plug
through the opening; adjust and reprint the coupon if necessary.

## Assemble the Controller Dock

1. Install the inserts and UNO Q as described above.
2. Add thin foam or TPU strips to the hub cradle if desired.
3. Route the hub's captive cable through the internal channel and connect it to
   the UNO Q.
4. Seat the hub in the open rear bay.
5. Confirm both long port faces, the Ethernet end, and the captive lead are free.
6. Connect the camera to a USB-A 3.0 port, power to the hub's USB-C PD input, and
   optional Ethernet.
7. Fit the lid, Matrix bezel, and branding, then add the rubber feet.

## Second check-in: inspect before power

Before switching on the Controller, confirm:

- the board is flat and no standoff is twisting it;
- screw heads and inserts cannot touch components or solder joints;
- the hub and USB-C cable are not pushing sideways on the UNO Q socket;
- the Matrix window and every ventilation opening are clear;
- no loose screw, wire strand, or printed debris remains inside; and
- the lid closes without pressure on the board, hub, or cables.

Power the assembled Controller for 30 minutes with the camera active. Check that
the case remains comfortable to touch, the camera stays connected, and the
Matrix and Dashboard behave normally. A warm board is expected; a softening PLA
case, repeated USB disconnect, or unusually hot enclosure is not.

## Make a revision

Open `virtualglove-controller.scad` in OpenSCAD. The dimensions and clearances
that are most likely to need adjustment are grouped at the top of the file.
Choose a part from the `part` selector, preview it, and export it directly, or
regenerate the complete checked-in STL set with:

```bash
hardware/enclosures/export-stl.sh
```

Keep the source file, STL files, and this guide together in a check-in. Note the
printer and measured fit when changing a hardware dimension so the next person
can tell whether the change is universal or printer-specific.

## Safety and limits

- Disconnect power before opening the case.
- Handle the UNO Q with normal electrostatic-discharge care.
- Never force the board, hub, plug, insert, or lid into place.
- Keep metal fasteners and decorative foil away from antennas and electronics.
- Keep airflow paths open and inspect PLA periodically in a warm cabinet.
- Treat this as a first-fit printable design until it has been measured against
  the exact hub, plugs, inserts, and printer that will be used.

The enclosure protects and organizes the Controller; it does not make the UNO Q
or hub waterproof, impact-rated, or suitable for outdoor use.
