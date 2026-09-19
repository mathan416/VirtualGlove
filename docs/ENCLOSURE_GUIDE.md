# VirtualGlove Controller Enclosure Guide

VirtualGlove now includes two printable homes for the Arduino UNO Q Controller.
Both were designed for an Anycubic Kobra 3, ordinary PLA, a 0.4 mm nozzle, and
the Arduino USB-C Hub (8 in 1).

The files are intentionally parametric. Print the small fit tests first, record
what changed, and adjust the clearances before committing to a long print.

## Choose your case

### UNO Q Case

![UNO Q Case exterior](../hardware/enclosures/previews/virtualglove-uno-case-exterior.png)

Choose the compact case when the Arduino hub will sit elsewhere in the arcade
panel. The case protects the UNO Q, exposes only its USB-C connection, keeps the
Matrix visible, and leaves airflow around the board.

- Outside size: approximately **90 x 76 x 27 mm** when assembled.
- Best for: a hidden Controller, short cable runs, or the smallest possible box.
- The USB-C hub, camera cable, power cable, and optional Ethernet cable remain
  outside the enclosure.

### Controller Dock

![Controller Dock exterior](../hardware/enclosures/previews/virtualglove-controller-dock-exterior.png)

Choose the Dock when the UNO Q and Arduino hub should move and mount as one
unit. The hub sits in an open service bay, so its USB, USB-C power, and Ethernet
connections remain reachable.

- Outside size: approximately **148 x 104 x 31 mm** when assembled.
- Best for: a neat arcade-panel installation or a Controller given as a complete
  unit.
- The hub remains removable; it is not trapped inside a sealed hot box.

| Compare | UNO Q Case | Controller Dock |
| --- | --- | --- |
| Hub location | Outside the case | Open rear service bay |
| Port access | UNO Q USB-C only | Hub USB, USB-C power, and Ethernet |
| Portability | Smallest enclosure | UNO Q and hub move together |
| Best fit | Hidden cabinet installation | Complete, transferable Controller |

For assembly at the workbench, use the
[two-page Enclosure Assembly Quick Reference](ENCLOSURE_QUICK_REFERENCE.md).
This guide adds print settings, fit checks, detailed explanations, and
troubleshooting.

<!-- PAGEBREAK -->

## What you need

VirtualGlove supplies the digital print files. The UNO Q, hub, fasteners,
inserts, tools, cables, adhesive, and other physical parts are not included.

### Shared hardware and tools

| Item | Quantity | Purpose |
| --- | ---: | --- |
| Arduino UNO Q | 1 | Runs VirtualGlove |
| Arduino USB-C Hub (8 in 1) | 1 | Camera, power, and optional Ethernet; external with the compact case |
| M3 x 8 mm board screws | 4 | Fasten the UNO Q to its standoffs |
| M3 x 8-12 mm case screws | 4 | Fasten the lid to the base |
| M3 heat-set inserts | 4 | Approximately 4.0-4.2 mm outside diameter; receive the case screws |
| Heat-set insert tool | 1 | Seats the inserts squarely |
| M3 driver | 1 | Installs the board and case screws |
| Adhesive rubber feet | 4 | Keeps the enclosure stable and allows bottom airflow |

### UNO Q Case print set

- [UNO Q base](../hardware/enclosures/stl/virtualglove-uno-base.stl)
- [UNO Q lid](../hardware/enclosures/stl/virtualglove-uno-lid.stl)
- [USB-C fit coupon](../hardware/enclosures/stl/virtualglove-usb-c-fit-coupon.stl)

The hub is still required, but it remains outside this enclosure and connects
through the broad USB-C opening.

### Controller Dock print set

- [Dock base](../hardware/enclosures/stl/virtualglove-dock-base.stl)
- [Dock lid](../hardware/enclosures/stl/virtualglove-dock-lid.stl)
- [USB-C fit coupon](../hardware/enclosures/stl/virtualglove-usb-c-fit-coupon.stl)
- [Hub fit coupon](../hardware/enclosures/stl/virtualglove-hub-fit-coupon.stl)

<!-- PAGEBREAK -->

### Shared finishing parts

The enclosure works without decorative pieces. The Matrix bezel is recommended
for a finished edge around the display; choose one emblem only if wanted.

| Finishing part | Downloads |
| --- | --- |
| Matrix bezel | [Cyan bezel](../hardware/enclosures/stl/virtualglove-matrix-bezel.stl) |
| Small lid emblem | [Dark backing](../hardware/enclosures/stl/virtualglove-lid-logo-backing.stl); [cyan hand and target](../hardware/enclosures/stl/virtualglove-lid-logo-cyan.stl); [red target beam](../hardware/enclosures/stl/virtualglove-lid-logo-red.stl) |
| Optional full-logo plaque | [Dark backing](../hardware/enclosures/stl/virtualglove-full-logo-backing.stl); [cyan hand and wordmark](../hardware/enclosures/stl/virtualglove-full-logo-cyan.stl); [red target accents](../hardware/enclosures/stl/virtualglove-full-logo-red.stl) |
| Optional larger emblem | [Dark backing](../hardware/enclosures/stl/virtualglove-target-badge-backing.stl); [cyan hand and target](../hardware/enclosures/stl/virtualglove-target-badge-cyan.stl); [red target beam](../hardware/enclosures/stl/virtualglove-target-badge-red.stl) |

### Optional materials and connections

- Thin double-sided adhesive or plastic-safe glue for the branding layers.
- Approximately 1 mm foam or TPU strips beneath the Dock's hub if it needs a
  quieter or firmer fit.
- A camera connected to a USB-A 3.0 port on the hub.
- USB-C PD power connected to the hub.
- Ethernet connected to the hub when a wired network is wanted.

The full-logo and hand/target pieces are printable adaptations of the project
artwork. They preserve the italic wordmark, hand, target, cyan linework, and red
accents while removing screen-only glow and details smaller than a dependable
0.4 mm nozzle can reproduce.

![Print-safe full logo and hand-target emblem](../hardware/enclosures/previews/virtualglove-printable-branding.png)

To change a dimension, download the
[parametric OpenSCAD source](../hardware/enclosures/virtualglove-controller.scad)
and the [STL export script](../hardware/enclosures/export-stl.sh).

## Prepare and print

### First check-in: print the coupons

Print the [USB-C fit coupon](../hardware/enclosures/stl/virtualglove-usb-c-fit-coupon.stl)
for either enclosure. If building the Dock, also print the
[hub fit coupon](../hardware/enclosures/stl/virtualglove-hub-fit-coupon.stl).

The USB-C plug should enter without scraping and should not have enough side
play to pull hard against the UNO Q socket. The hub should sit in its channel
without bowing the Dock coupon or rattling loosely.

Record the printer, material, nozzle, slicer profile, and any dimensional change
you make. In `virtualglove-controller.scad`, `fit` controls ordinary mating
clearance and `hub_fit` controls the hub cradle. Do not scale the entire model
to fix one opening; change the relevant clearance instead.

### Kobra 3 PLA starting profile

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

### Dimensions and reference drawings

The design follows Arduino's published **68.58 x 53.34 mm** UNO Q outline and
four mounting holes. The hub envelope is **119 x 27.8 x 16 mm** with a fixed
175 mm cable. Arduino does not publish every plug-body and overmould dimension,
which is why the fit coupons are part of the build rather than an optional
extra.

- [Arduino UNO Q datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-datasheet.pdf)
- [Arduino UNO Q STEP model](https://docs.arduino.cc/resources/models/ABX00162-step.zip)
- [Arduino USB-C Hub datasheet](https://docs.arduino.cc/resources/datasheets/TPX00241-datasheet.pdf)

### Printing the branding

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

## Understand and assemble

### Rear and side views

Left and right are named while looking at the Controller from the front/Matrix
side. The UNO Q Case views expose the broad USB-C opening. The Dock views show
how the open hub bay remains reachable from both sides and the rear.

| View | UNO Q Case | Controller Dock |
| --- | --- | --- |
| Rear | <img src="../hardware/enclosures/previews/virtualglove-uno-case-back.png" alt="Rear view of the UNO Q Case" width="240" /> | <img src="../hardware/enclosures/previews/virtualglove-controller-dock-back.png" alt="Rear view of the Controller Dock" width="240" /> |
| Left | <img src="../hardware/enclosures/previews/virtualglove-uno-case-left.png" alt="Left-side view of the UNO Q Case" width="240" /> | <img src="../hardware/enclosures/previews/virtualglove-controller-dock-left.png" alt="Left-side view of the Controller Dock" width="240" /> |
| Right | <img src="../hardware/enclosures/previews/virtualglove-uno-case-right.png" alt="Right-side view of the UNO Q Case" width="240" /> | <img src="../hardware/enclosures/previews/virtualglove-controller-dock-right.png" alt="Right-side view of the Controller Dock" width="240" /> |

### Exploded assembly

These views show the assembly order rather than print orientation. Fasteners
and heat-set inserts are omitted so the main layers remain easy to see. In the
Dock view, the hub is pulled to the right to reveal its cradle and accessible
port face; it slides back into the open rear bay during assembly.

| UNO Q Case | Controller Dock |
| --- | --- |
| <img src="../hardware/enclosures/previews/virtualglove-uno-case-exploded.png" alt="Exploded assembly view of the UNO Q Case" width="320" /> | <img src="../hardware/enclosures/previews/virtualglove-controller-dock-exploded.png" alt="Exploded assembly view of the Controller Dock" width="320" /> |

Keep the
[two-page Enclosure Assembly Quick Reference](ENCLOSURE_QUICK_REFERENCE.md)
beside the workbench for the visual sequence. The detailed steps below explain
the fit checks that accompany it.

### Assemble the UNO Q Case

1. Heat the four inserts into the corner bosses. Keep them square and stop when
   they are flush; excess heat can soften the boss.
2. Fasten the UNO Q to the four standoffs with the USB-C socket facing the
   broad opening.
3. Connect the Arduino hub through that opening.
4. Dry-fit the lid and confirm the plug does not press on the socket.
5. Add the Matrix bezel and preferred emblem, if used.
6. Fasten the lid and add the rubber feet.

Only the UNO Q USB-C port is intentionally exposed. Do not force a thick plug
through the opening; adjust and reprint the coupon if necessary.

### Assemble the Controller Dock

1. Heat the four inserts into the corner bosses, keeping them square and flush.
2. Fasten the UNO Q to its standoffs with the USB-C socket facing the broad
   opening.
3. Add thin foam or TPU strips to the hub cradle if desired.
4. Route the hub's captive cable through the internal channel and connect it to
   the UNO Q.
5. Seat the hub in the open rear bay.
6. Confirm both long port faces, the Ethernet end, and the captive lead are
   free.
7. Connect the camera to a USB-A 3.0 port, power to the hub's USB-C PD input, and
   optional Ethernet.
8. Fit the lid, Matrix bezel, and preferred emblem, then add the rubber feet.

### Second check-in: inspect before power

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

## Customize and maintain

### Make a revision

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

### Safety and limits

- Disconnect power before opening the case.
- Handle the UNO Q with normal electrostatic-discharge care.
- Never force the board, hub, plug, insert, or lid into place.
- Keep metal fasteners and decorative foil away from antennas and electronics.
- Keep airflow paths open and inspect PLA periodically in a warm cabinet.
- Treat this as a first-fit printable design until it has been measured against
  the exact hub, plugs, inserts, and printer that will be used.

The enclosure protects and organizes the Controller; it does not make the UNO Q
or hub waterproof, impact-rated, or suitable for outdoor use.
