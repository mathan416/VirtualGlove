// VirtualGlove Controller enclosures
// SPDX-License-Identifier: MIT
// Designed for the Arduino UNO Q and Arduino USB-C Hub (8 in 1).
// Generate a part with, for example:
//   openscad -D 'part="uno_base"' -o stl/virtualglove-uno-base.stl virtualglove-controller.scad

$fn = 48;
part = "assembly_preview";

// Printer/material tuning ----------------------------------------------------
wall = 2.4;
floor_t = 2.4;
top_t = 2.4;
fit = 0.35;                 // general PLA clearance per mating surface
insert_d = 4.15;            // starting point for M3 heat-set inserts
screw_d = 3.25;

// Arduino UNO Q official mechanical dimensions ------------------------------
uno_w = 68.58;
uno_d = 53.34;
uno_bottom_clearance = 2.0;
uno_standoff_top = 7.0;
uno_standoff_d = 5.4;       // narrow top clears UNO Q underside hardware
uno_standoff_foot_d = 6.4;  // short foot retains strength at the floor
uno_standoff_foot_h = 1.6;
lid_boss_relief_d = 9.2;    // 8 mm boss plus fit clearance on both sides
uno_holes = [
    [15.24, 53.34 - 6.40],
    [13.97, 2.54],
    [68.58 - 2.54, 53.34 - 17.78],
    [68.58 - 2.54, 7.62]
];

// Arduino USB-C Hub (8 in 1) official envelope ------------------------------
hub_l = 119.0;
hub_w = 27.8;
hub_h = 16.0;
hub_fit = 0.50;

// Compact UNO Q enclosure ----------------------------------------------------
uno_case_w = 90;
uno_case_d = 76;
uno_base_h = 21;
uno_corner = 5;
uno_x = (uno_case_w - uno_w) / 2;
uno_y = (uno_case_d - uno_d) / 2;

// Integrated Controller Dock ------------------------------------------------
dock_w = 148;
dock_d = 104;
dock_base_h = 25;
dock_corner = 6;
dock_uno_x = (dock_w - uno_w) / 2;
dock_uno_y = 8.5;
hub_x = (dock_w - hub_l) / 2;
hub_y = 70.0;
hub_bottom = 9.5;

// Controller Dock V2 -------------------------------------------------------
// V2 fully encloses the hub. The USB-C bank faces rear access openings. Cables
// attached to the opposite USB-A/HDMI bank are fitted before the lid closes
// and leave through rear routing notches on either side of the hub.
dock_v2_w = 160;
dock_v2_d = 122;
dock_v2_base_h = 33;
dock_v2_corner = 6;
dock_v2_uno_x = (dock_v2_w - uno_w) / 2 + 8.0;
dock_v2_uno_y = 8.5;
// Put the RJ45 end beside its wall opening. This also leaves a useful bend
// bay at the captive-cable end instead of trapping it against the left wall.
hub_v2_x = dock_v2_w - wall - hub_l - 0.6;
hub_v2_y = dock_v2_d - wall - hub_w - 0.6;
hub_v2_bottom = 11.5;
hub_v2_platform_t = 2.6;
hub_v2_rail_h = 1.6;

module rounded_prism(size, r) {
    hull() {
        for (x = [r, size[0] - r])
            for (y = [r, size[1] - r])
                translate([x, y, 0]) cylinder(h = size[2], r = r);
    }
}

module slot(length, width, height) {
    hull() {
        translate([width / 2, width / 2, 0]) cylinder(h = height, d = width);
        translate([length - width / 2, width / 2, 0]) cylinder(h = height, d = width);
    }
}

module vent_field(origin, columns, rows, pitch_x = 7, pitch_y = 6, length = 5, width = 2) {
    for (row = [0 : rows - 1])
        for (column = [0 : columns - 1])
            translate([origin[0] + column * pitch_x, origin[1] + row * pitch_y, origin[2]])
                slot(length, width, origin[3]);
}

module board_standoffs(origin) {
    for (hole = uno_holes)
        translate([origin[0] + hole[0], origin[1] + hole[1], floor_t])
            difference() {
                union() {
                    cylinder(h = uno_standoff_top - floor_t,
                             d = uno_standoff_d);
                    cylinder(h = uno_standoff_foot_h,
                             d = uno_standoff_foot_d);
                }
                translate([0, 0, 0.8]) cylinder(h = uno_standoff_top, d = 2.7);
            }
}

module case_bosses(size, height) {
    for (p = [[6.3, 6.3], [size[0] - 6.3, 6.3],
              [6.3, size[1] - 6.3], [size[0] - 6.3, size[1] - 6.3]])
        translate([p[0], p[1], floor_t])
            difference() {
                cylinder(h = height - floor_t - 0.8, d = 8.0);
                translate([0, 0, height - floor_t - 6.8])
                    cylinder(h = 7.0, d = insert_d);
            }
}

module lid_screw_holes(size, height) {
    for (p = [[6.3, 6.3], [size[0] - 6.3, 6.3],
              [6.3, size[1] - 6.3], [size[0] - 6.3, size[1] - 6.3]]) {
        translate([p[0], p[1], -0.2]) cylinder(h = height + 0.4, d = screw_d);
        translate([p[0], p[1], -0.2]) cylinder(h = 1.35, d = 6.4);
    }
}

module lid_boss_reliefs(size, skirt_h) {
    // The lid skirt must pass around, not through, the four insert bosses.
    // Start at the underside of the top panel so the visible lid stays whole.
    for (p = [[6.3, 6.3], [size[0] - 6.3, 6.3],
              [6.3, size[1] - 6.3], [size[0] - 6.3, size[1] - 6.3]])
        translate([p[0], p[1], top_t - 0.05])
            cylinder(h = skirt_h + 0.1, d = lid_boss_relief_d);
}

module lid_usb_c_relief(board_y, skirt_h) {
    // Continue the broad USB-C opening through the lid skirt. Thick moulded
    // plugs then use the full opening and do not have to bend around the lip.
    translate([-0.2, board_y + 20.5, top_t - 0.05])
        cube([wall + fit + 4.0, 31.0, skirt_h + 0.1]);
}

module base_shell(size, height, corner) {
    difference() {
        rounded_prism([size[0], size[1], height], corner);
        translate([wall, wall, floor_t])
            rounded_prism([size[0] - 2 * wall, size[1] - 2 * wall,
                           height - floor_t + 0.2], max(1, corner - wall));
    }
}

module lid_shell(size, skirt_h, corner) {
    difference() {
        union() {
            rounded_prism([size[0], size[1], top_t], corner);
            translate([wall + fit, wall + fit, top_t])
                difference() {
                    rounded_prism([size[0] - 2 * (wall + fit),
                                   size[1] - 2 * (wall + fit), skirt_h],
                                  max(1, corner - wall - fit));
                    translate([1.8, 1.8, -0.1])
                        rounded_prism([size[0] - 2 * (wall + fit + 1.8),
                                       size[1] - 2 * (wall + fit + 1.8), skirt_h + 0.2],
                                      max(0.8, corner - wall - fit - 1.8));
                }
        }
        lid_screw_holes(size, top_t + skirt_h);
        lid_boss_reliefs(size, skirt_h);
    }
}

// Lids are exported exterior-face-down for clean, support-free printing. Mirror
// top features in Y so they align with the board after the lid is flipped over
// for assembly.
module print_face_transform(depth) {
    translate([0, depth, 0]) mirror([0, 1, 0]) children();
}

module broad_uno_usb_opening(board_y, height) {
    // Wide on purpose: it accepts both slim and overmoulded USB-C hub plugs.
    translate([-0.2, board_y + 21.5, 6.0])
        cube([wall + 0.5, 29.0, min(13.5, height - 6.0) + 0.2]);
}

module bottom_vents(board_origin, z_height) {
    vent_field([board_origin[0] + 25, board_origin[1] + 8, -0.2, z_height],
               4, 3, 7, 6, 5, 2);
}

module matrix_window(board_origin, z_height) {
    // Window is intentionally generous around the UNO Q matrix area.
    translate([board_origin[0] + 27.5, board_origin[1] + 6.5, -0.2])
        cube([29.5, 19.5, z_height + 0.4]);
}

module lid_logo_recess(size, y, z_height, recess_size = [18.5, 18.5]) {
    translate([(size[0] - recess_size[0]) / 2, y, -0.1])
        rounded_prism([recess_size[0], recess_size[1],
                       min(0.85, z_height) + 0.1], 2.2);
}

// The compact UNO Q enclosure cannot accept the 100 mm plaque. Its wordmark
// uses the 76 mm insert. Both dock lids use the actual 100 x 30 mm full logo,
// with 0.4 mm clearance on every side for an ordinary PLA print.
compact_wordmark_recess = [76.5, 23.3];
full_wordmark_recess = [100.8, 30.8];

module uno_base() {
    difference() {
        union() {
            base_shell([uno_case_w, uno_case_d], uno_base_h, uno_corner);
            board_standoffs([uno_x, uno_y]);
            case_bosses([uno_case_w, uno_case_d], uno_base_h);
        }
        broad_uno_usb_opening(uno_y, uno_base_h);
        bottom_vents([uno_x, uno_y], floor_t + 0.4);
    }
}

module uno_lid(full_logo = false) {
    difference() {
        lid_shell([uno_case_w, uno_case_d], 6.0, uno_corner);
        print_face_transform(uno_case_d) {
            lid_usb_c_relief(uno_y, 6.0);
            matrix_window([uno_x, uno_y], top_t + 0.2);
            if (full_logo)
                lid_logo_recess([uno_case_w, uno_case_d], 41.0, top_t,
                                compact_wordmark_recess);
            else
                lid_logo_recess([uno_case_w, uno_case_d], 54.0, top_t);
            if (full_logo)
                vent_field([uno_x + 8, 5.0, -0.2, top_t + 0.4],
                           7, 2, 7, 5, 5, 2);
            else
                vent_field([uno_x + 8, uno_y + 32, -0.2, top_t + 0.4],
                           7, 2, 7, 6, 5, 2);
        }
    }
}

module hub_cradle() {
    // Low rails grip the lower shell without covering either long port face.
    translate([hub_x - 1.3, hub_y - 1.3, floor_t])
        cube([hub_l + 2.6, hub_w + 2.6, hub_bottom - floor_t]);
    translate([hub_x - 1.3, hub_y - 1.3, hub_bottom])
        cube([hub_l + 2.6, 1.8, 4.2]);
    translate([hub_x - 1.3, hub_y + hub_w - 0.5, hub_bottom])
        cube([hub_l + 2.6, 1.8, 4.2]);
    // Low corner stops leave the captive lead and RJ45 end unobstructed.
    for (x = [hub_x - 1.3, hub_x + hub_l - 2.0])
        for (y = [hub_y - 1.3, hub_y + hub_w - 2.0])
            translate([x, y, hub_bottom]) cube([3.3, 3.3, 5.0]);
}

module hub_v2_cradle() {
    // The low cradle holds the hidden hub below the lid. Rails touch only the
    // lower shell and stay below both connector banks.
    platform_z = hub_v2_bottom - hub_v2_platform_t;
    translate([hub_v2_x - 1.3, hub_v2_y - 1.3, floor_t])
        cube([hub_l + 2.6, hub_w + 2.6, platform_z - floor_t]);
    translate([hub_v2_x - 1.3, hub_v2_y - 1.3, platform_z])
        cube([hub_l + 2.6, hub_w + 2.6, hub_v2_platform_t]);
    translate([hub_v2_x - 1.3, hub_v2_y - 1.3, hub_v2_bottom])
        cube([hub_l + 2.6, 1.8, hub_v2_rail_h]);
    translate([hub_v2_x - 1.3, hub_v2_y + hub_w - 0.5, hub_v2_bottom])
        cube([hub_l + 2.6, 1.8, hub_v2_rail_h]);
}

module dock_base() {
    difference() {
        union() {
            base_shell([dock_w, dock_d], dock_base_h, dock_corner);
            board_standoffs([dock_uno_x, dock_uno_y]);
            case_bosses([dock_w, dock_d], dock_base_h);
            hub_cradle();
        }
        broad_uno_usb_opening(dock_uno_y, dock_base_h);
        bottom_vents([dock_uno_x, dock_uno_y], floor_t + 0.4);
        // Cable channel from the hub's captive lead into the board bay.
        translate([hub_x - 2, hub_y + hub_w / 2 - 5, hub_bottom - 1])
            cube([22, 10, 9]);
    }
}

module dock_lid(full_logo = false) {
    difference() {
        lid_shell([dock_w, dock_d], 6.0, dock_corner);
        print_face_transform(dock_d) {
            lid_usb_c_relief(dock_uno_y, 6.0);
            matrix_window([dock_uno_x, dock_uno_y], top_t + 0.2);
            if (full_logo)
                lid_logo_recess([dock_w, dock_d], 39.0, top_t,
                                full_wordmark_recess);
            else
                lid_logo_recess([dock_w, dock_d], 44.0, top_t);
            if (full_logo)
                vent_field([dock_uno_x + 6, 4.0, -0.2, top_t + 0.4],
                           8, 2, 7, 5, 5, 2);
            else
                vent_field([dock_uno_x + 6, dock_uno_y + 31,
                            -0.2, top_t + 0.4], 8, 2, 7, 6, 5, 2);
            // Open bay around all hub faces, including Ethernet and cable ends.
            translate([hub_x - 4.0, hub_y - 7.0, -0.2])
                cube([hub_l + 8.0, hub_w + 14.0, top_t + 7]);
        }
    }
}

module dock_v2_base() {
    difference() {
        union() {
            base_shell([dock_v2_w, dock_v2_d], dock_v2_base_h, dock_v2_corner);
            board_standoffs([dock_v2_uno_x, dock_v2_uno_y]);
            case_bosses([dock_v2_w, dock_v2_d], dock_v2_base_h);
            hub_v2_cradle();
        }
        bottom_vents([dock_v2_uno_x, dock_v2_uno_y], floor_t + 0.4);
        // Rear access for the outward-facing USB-C PD and data bank. Arduino
        // does not publish plug-overmould dimensions, so this is deliberately
        // one generous service opening rather than two tightly fitted holes.
        translate([hub_v2_x + 14, dock_v2_d - wall - 0.2,
                   hub_v2_bottom + 2.4])
            cube([91, wall + 0.5, 11.2]);
        // Cables plugged into the inward-facing USB-A/HDMI bank turn around
        // the hub ends and leave through these rear strain-relief openings.
        for (x = [4.0, dock_v2_w - 16.0])
            translate([x, dock_v2_d - wall - 0.2, 7.0])
                cube([12.0, wall + 0.5, 15.0]);
        // The hub is installed with its RJ45 socket facing the right wall.
        // This side opening accepts the Ethernet plug without opening the lid.
        translate([dock_v2_w - wall - 0.2,
                   hub_v2_y + (hub_w - 18.0) / 2,
                   hub_v2_bottom + 0.5])
            cube([wall + 0.5, 18.0, 16.5]);
        // Internal channel for the hub's captive UNO Q cable.
        translate([hub_v2_x - 2, hub_v2_y + hub_w / 2 - 6, 6.0])
            cube([24, 12, hub_v2_bottom + 3]);
    }
}

module dock_v2_lid(full_logo = false) {
    // A complete lid hides the hub. Only the Matrix window and ventilation
    // remain on top; every cable leaves through the rear base openings.
    difference() {
        lid_shell([dock_v2_w, dock_v2_d], 6.0, dock_v2_corner);
        print_face_transform(dock_v2_d) {
            lid_usb_c_relief(dock_v2_uno_y, 6.0);
            matrix_window([dock_v2_uno_x, dock_v2_uno_y], top_t + 0.2);
            if (full_logo)
                lid_logo_recess([dock_v2_w, dock_v2_d], 52.0, top_t,
                                full_wordmark_recess);
            else
                lid_logo_recess([dock_v2_w, dock_v2_d], 44.0, top_t);
            vent_field([dock_v2_uno_x + 6, dock_v2_uno_y + 31,
                        -0.2, top_t + 0.4], 8, 2, 7, 6, 5, 2);
        }
    }
}

module matrix_bezel() {
    difference() {
        rounded_prism([33.0, 23.0, 1.2], 2.2);
        translate([1.75, 1.75, -0.1]) cube([29.5, 19.5, 1.4]);
    }
}

module printable_hand_2d() {
    // Bold silhouette derived from the hand/target mark.  Minimum finger and
    // wrist widths are deliberately generous for a 0.4 mm nozzle.
    union() {
        polygon(points=[[-5.8,-7],[-7,-1],[-6,5],[6,5],[8,0],[7,-5],[4.5,-8],[-2,-8]]);
        hull() { translate([-4.7,3]) circle(r=1.35); translate([-5.2,13]) circle(r=1.35); }
        hull() { translate([-1.8,3]) circle(r=1.4); translate([-1.8,16]) circle(r=1.4); }
        hull() { translate([1.3,3]) circle(r=1.4); translate([1.5,14.5]) circle(r=1.4); }
        hull() { translate([4.3,2.5]) circle(r=1.3); translate([5.3,11.5]) circle(r=1.3); }
        hull() { translate([-5.3,0]) circle(r=1.45); translate([-11,5.5]) circle(r=1.45); }
    }
}

module target_corners_2d() {
    for (sx = [-1, 1])
        for (sy = [-1, 1]) {
            translate([sx * 10.0, sy * 10.0])
                rotate(sx < 0 ? (sy < 0 ? 0 : -90) : (sy < 0 ? 90 : 180))
                    union() {
                        square([5.2, 1.4]);
                        square([1.4, 5.2]);
                    }
        }
}

module hand_target_mark(height = 0.9) {
    linear_extrude(height = height)
        difference() {
            union() {
                printable_hand_2d();
                target_corners_2d();
                difference() { circle(r = 4.4); circle(r = 2.5); }
            }
            // Open the palm around the target so the mark remains legible.
            circle(r = 2.1);
        }
}

branding_backing_h = 0.8;
branding_insert_h = 0.5;
branding_pocket_floor = 0.3;
branding_insert_fit = 0.12;

module target_badge_cyan_2d() {
    difference() {
        translate([14, 12.0]) scale([0.82, 0.82])
            projection(cut = false) hand_target_mark(0.1);
        translate([2.6, 11.45]) square([22.8, 1.1]);
    }
}

module target_badge_red_2d() {
    // The target beam and three terminal pixels are separate for economical
    // ACE Pro colour changes or a glued two-colour assembly.
    translate([2.8, 11.55]) square([22.4, 0.9]);
    for (x = [22.0, 24.0, 26.0])
        translate([x, 10.9]) square([1.0, 2.2]);
}

module target_badge_backing() {
    difference() {
        rounded_prism([28, 28, branding_backing_h], 3.0);
        translate([0, 0, branding_pocket_floor])
            linear_extrude(height = branding_backing_h)
                offset(delta = branding_insert_fit)
                    union() {
                        target_badge_cyan_2d();
                        target_badge_red_2d();
                    }
    }
}

module target_badge_cyan() {
    linear_extrude(height = branding_insert_h) target_badge_cyan_2d();
}

module target_badge_red() {
    linear_extrude(height = branding_insert_h) target_badge_red_2d();
}

module lid_logo_backing() {
    scale([18 / 28, 18 / 28, 1]) target_badge_backing();
}

module lid_logo_cyan() {
    scale([18 / 28, 18 / 28, 1]) target_badge_cyan();
}

module lid_logo_red() {
    scale([18 / 28, 18 / 28, 1]) target_badge_red();
}

module full_logo_cyan_2d() {
    difference() {
        translate([14, 13.0]) scale([0.72, 0.72])
            projection(cut = false) hand_target_mark(0.1);
        translate([4.3, 12.45]) square([20.0, 1.1]);
    }
    translate([27, 17.0])
        text("VirtualGlove", size = 7.7, valign = "center",
             font = "Liberation Sans:style=Bold Italic");
    translate([28, 8.0]) square([55, 1.3]);
}

module full_logo_red_2d() {
    translate([4.5, 12.55]) square([19, 0.9]);
    for (x = [86, 89, 92])
        translate([x, 7.5]) square([1.8, 2.2]);
}

module full_logo_backing() {
    difference() {
        rounded_prism([100, 30, branding_backing_h], 3.0);
        translate([0, 0, branding_pocket_floor])
            linear_extrude(height = branding_backing_h)
                offset(delta = branding_insert_fit)
                    union() {
                        full_logo_cyan_2d();
                        full_logo_red_2d();
                    }
    }
}

module full_logo_cyan() {
    linear_extrude(height = branding_insert_h) full_logo_cyan_2d();
}

module full_logo_red() {
    linear_extrude(height = branding_insert_h) full_logo_red_2d();
}

module compact_full_logo_backing() {
    scale([0.76, 0.76, 1]) full_logo_backing();
}

module compact_full_logo_cyan() {
    scale([0.76, 0.76, 1]) full_logo_cyan();
}

module compact_full_logo_red() {
    scale([0.76, 0.76, 1]) full_logo_red();
}

module target_badge_multicolor() {
    color("#111722") target_badge_backing();
    color("#00d6ef") translate([0, 0, branding_pocket_floor])
        target_badge_cyan();
    color("#ff2145") translate([0, 0, branding_pocket_floor])
        target_badge_red();
}

module lid_logo_multicolor() {
    color("#111722") lid_logo_backing();
    color("#00d6ef") translate([0, 0, branding_pocket_floor])
        lid_logo_cyan();
    color("#ff2145") translate([0, 0, branding_pocket_floor])
        lid_logo_red();
}

module full_logo_multicolor() {
    color("#111722") full_logo_backing();
    color("#00d6ef") translate([0, 0, branding_pocket_floor])
        full_logo_cyan();
    color("#ff2145") translate([0, 0, branding_pocket_floor])
        full_logo_red();
}

module compact_full_logo_multicolor() {
    color("#111722") compact_full_logo_backing();
    color("#00d6ef") translate([0, 0, branding_pocket_floor])
        compact_full_logo_cyan();
    color("#ff2145") translate([0, 0, branding_pocket_floor])
        compact_full_logo_red();
}

module branding_preview() {
    color("#111722") full_logo_backing();
    color("#00d6ef") translate([0, 0, branding_pocket_floor]) full_logo_cyan();
    color("#ff2145") translate([0, 0, branding_pocket_floor]) full_logo_red();
    translate([106, 1, 0]) {
        color("#111722") target_badge_backing();
        color("#00d6ef") translate([0, 0, branding_pocket_floor]) target_badge_cyan();
        color("#ff2145") translate([0, 0, branding_pocket_floor]) target_badge_red();
    }
}

module branding_insets_preview() {
    // Pocketed backings and their loose inserts are separated for a clear
    // assembly illustration; all pieces remain in their print orientation.
    color("#59616b") full_logo_backing();
    color("#00d6ef") translate([0, 36, 0]) full_logo_cyan();
    color("#ff2145") translate([0, 50, 0]) full_logo_red();
    translate([108, 0, 0]) {
        color("#59616b") target_badge_backing();
        color("#00d6ef") translate([0, 36, 0]) target_badge_cyan();
        color("#ff2145") translate([0, 50, 0]) target_badge_red();
    }
}

module usb_c_fit_coupon() {
    // Tests the intended 29 x 13.5 mm broad plug opening and wall thickness.
    difference() {
        rounded_prism([38, 24, 8], 3);
        translate([4.5, -0.2, 2.0]) cube([29, wall + 0.5, 6.2]);
        translate([8, wall, 2.0]) cube([22, 24, 6.2]);
    }
}

module hub_fit_coupon() {
    // A 35 mm slice of the cradle; print this before committing to the Dock.
    coupon_l = 35;
    difference() {
        rounded_prism([coupon_l, hub_w + 2 * (1.3 + hub_fit), 7], 2);
        translate([2, 1.3 + hub_fit, 2.2])
            cube([coupon_l - 4, hub_w, 6]);
    }
}

module board_proxy(origin = [0, 0], show_hub = false) {
    color("#008184") translate([origin[0], origin[1], uno_standoff_top])
        cube([uno_w, uno_d, 1.6]);
    color("silver")
        for (hole = uno_holes)
            translate([origin[0] + hole[0], origin[1] + hole[1], uno_standoff_top - 0.2])
                cylinder(h = 2.0, d = 3.2);
    if (show_hub)
        color("#20242a") translate([hub_x, hub_y, hub_bottom])
            cube([hub_l, hub_w, hub_h]);
}

module hub_proxy_v2(bottom = hub_v2_bottom) {
    // Contrasting blocks identify the hidden hub's connector banks in cutaway
    // documentation renders. They are not printable geometry.
    color("#20242a") translate([hub_v2_x, hub_v2_y, bottom])
        cube([hub_l, hub_w, hub_h]);
    // Rear-facing USB-C bank: PD power and USB-C data.
    color("#ff2145") translate([hub_v2_x + 27, hub_v2_y + hub_w - 0.2,
                                bottom + 5.3])
        cube([10, 1.0, 4.8]);
    color("#00b9d8") translate([hub_v2_x + 48, hub_v2_y + hub_w - 0.2,
                                bottom + 5.3])
        cube([10, 1.0, 4.8]);
    // Inward-facing bank: HDMI plus USB-A 2.0 and USB-A 3.0.
    color("#c8ccd1") translate([hub_v2_x + 16, hub_v2_y - 0.8, bottom + 4.5])
        cube([15, 1.0, 6.5]);
    color("#c8ccd1") translate([hub_v2_x + 49, hub_v2_y - 0.8, bottom + 4.5])
        cube([15, 1.0, 6.5]);
    color("#00b9d8") translate([hub_v2_x + 77, hub_v2_y - 0.8, bottom + 4.5])
        cube([15, 1.0, 6.5]);
    // RJ45 Ethernet at the right end.
    color("#c8ccd1") translate([hub_v2_x + hub_l - 0.2,
                                hub_v2_y + 8.4, bottom + 2.8])
        cube([1.0, 11.0, 10.5]);
}

module hub_v2_plug_proxies(bottom = hub_v2_bottom) {
    // Representative overmoulds show direct rear USB-C access plus one USB-A
    // plug fitted internally before closure. These never enter an STL.
    color("#ff2145") translate([hub_v2_x + 26, hub_v2_y + hub_w,
                                bottom + 4.8])
        cube([12, 22, 5.8]);
    color("#00b9d8") translate([hub_v2_x + 47, hub_v2_y + hub_w,
                                bottom + 4.8])
        cube([12, 22, 5.8]);
    color("#00b9d8") translate([hub_v2_x + 76, hub_v2_y - 22, bottom + 4.0])
        cube([17, 22, 7.5]);
    color("#c8ccd1") translate([hub_v2_x + hub_l,
                                hub_v2_y + 7.8, bottom + 2.3])
        cube([25, 12.0, 11.5]);
    // Simplified internal cable route from the USB-A plug toward the right
    // rear strain-relief opening.
    color("#20242a") {
        translate([hub_v2_x + 91, hub_v2_y - 13, bottom + 6.2])
            cube([dock_v2_w - (hub_v2_x + 91) - 7, 4, 4]);
        translate([dock_v2_w - 11, hub_v2_y - 13, bottom + 6.2])
            cube([4, dock_v2_d - (hub_v2_y - 13), 4]);
    }
}

module assembly_preview() {
    color("#20242a") uno_base();
    board_proxy([uno_x, uno_y]);
    color([0.15, 0.15, 0.17, 0.45])
        translate([0, uno_case_d, uno_base_h + top_t]) rotate([180, 0, 0]) uno_lid();
    color("#00b9d8") translate([uno_x + 25.75, uno_y + 4.75, uno_base_h + top_t + 0.05])
        matrix_bezel();
}

module dock_preview() {
    color("#20242a") dock_base();
    board_proxy([dock_uno_x, dock_uno_y], true);
    color([0.15, 0.15, 0.17, 0.45])
        translate([0, dock_d, dock_base_h + top_t]) rotate([180, 0, 0]) dock_lid();
}

module dock_v2_preview() {
    color("#20242a") dock_v2_base();
    board_proxy([dock_v2_uno_x, dock_v2_uno_y]);
    hub_proxy_v2();
    color([0.15, 0.15, 0.17, 0.45])
        translate([0, dock_v2_d, dock_v2_base_h + top_t])
            rotate([180, 0, 0]) dock_v2_lid();
}

module uno_exterior_preview() {
    color("#20242a") uno_base();
    color("#2a2d33")
        translate([0, uno_case_d, uno_base_h + top_t]) rotate([180, 0, 0]) uno_lid();
    color("#00b9d8")
        translate([uno_x + 25.75, uno_y + 4.75, uno_base_h + top_t + 0.05])
            matrix_bezel();
    translate([(uno_case_w - 18) / 2, 54.25, uno_base_h + top_t - 0.8]) {
        color("#111722") lid_logo_backing();
        color("#00d6ef") translate([0, 0, branding_pocket_floor]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, branding_pocket_floor]) lid_logo_red();
    }
}

module dock_exterior_preview() {
    color("#20242a") dock_base();
    color("#2a2d33")
        translate([0, dock_d, dock_base_h + top_t]) rotate([180, 0, 0]) dock_lid();
    color("#16191d") translate([hub_x, hub_y, hub_bottom])
        cube([hub_l, hub_w, hub_h]);
    color("#00b9d8")
        translate([dock_uno_x + 25.75, dock_uno_y + 4.75, dock_base_h + top_t + 0.05])
            matrix_bezel();
    translate([(dock_w - 18) / 2, 44.25, dock_base_h + top_t - 0.8]) {
        color("#111722") lid_logo_backing();
        color("#00d6ef") translate([0, 0, branding_pocket_floor]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, branding_pocket_floor]) lid_logo_red();
    }
}

module dock_v2_exterior_preview() {
    color("#20242a") dock_v2_base();
    color("#2a2d33")
        translate([0, dock_v2_d, dock_v2_base_h + top_t])
            rotate([180, 0, 0]) dock_v2_lid();
    // Kept inside the opaque shell so the rear openings show their purpose.
    hub_proxy_v2();
    color("#00b9d8")
        translate([dock_v2_uno_x + 25.75, dock_v2_uno_y + 4.75,
                   dock_v2_base_h + top_t + 0.05])
            matrix_bezel();
    translate([(dock_v2_w - 18) / 2, 44.25,
               dock_v2_base_h + top_t - 0.8]) {
        color("#111722") lid_logo_backing();
        color("#00d6ef") translate([0, 0, branding_pocket_floor]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, branding_pocket_floor]) lid_logo_red();
    }
}

module dock_v2_port_access_preview() {
    // A translucent lid reveals the inward-facing USB-A connection and its
    // cable route while the rear-facing USB-C plugs remain directly usable.
    color("#20242a") dock_v2_base();
    board_proxy([dock_v2_uno_x, dock_v2_uno_y]);
    hub_proxy_v2();
    hub_v2_plug_proxies();
    color([0.15, 0.15, 0.17, 0.30])
        translate([0, dock_v2_d, dock_v2_base_h + top_t])
            rotate([180, 0, 0]) dock_v2_lid();
}

module lid_logo_options_preview() {
    // Two closed V2 lids show the selectable branding recesses. The left uses
    // the compact hand/target mark; the right uses the full wordmark.
    color("#2a2d33")
        translate([0, dock_v2_d, top_t]) rotate([180, 0, 0])
            dock_v2_lid(false);
    translate([(dock_v2_w - 18) / 2, 44.25, top_t - branding_backing_h])
        lid_logo_multicolor();

    translate([dock_v2_w + 20, 0, 0]) {
        color("#2a2d33")
            translate([0, dock_v2_d, top_t]) rotate([180, 0, 0])
                dock_v2_lid(true);
        translate([(dock_v2_w - 100) / 2, 52.4,
                   top_t - branding_backing_h])
            full_logo_multicolor();
    }
}

module uno_lid_logo_options_preview() {
    // The compact enclosure has its own correctly scaled wordmark option. Do
    // not reuse the dock illustration: the dock accepts the 100 mm plaque.
    color("#2a2d33")
        translate([0, uno_case_d, top_t]) rotate([180, 0, 0])
            uno_lid(false);
    translate([(uno_case_w - 18) / 2, 54.25,
               top_t - branding_backing_h])
        lid_logo_multicolor();

    translate([uno_case_w + 20, 0, 0]) {
        color("#2a2d33")
            translate([0, uno_case_d, top_t]) rotate([180, 0, 0])
                uno_lid(true);
        translate([(uno_case_w - 76) / 2, 41.25,
                   top_t - branding_backing_h])
            compact_full_logo_multicolor();
    }
}

module uno_back_preview() {
    // Keep the same presentation angle while exposing the connector side.
    translate([uno_case_w, uno_case_d, 0]) rotate([0, 0, 180])
        uno_exterior_preview();
}

module dock_back_preview() {
    // Rotate the assembled Dock so the hub service bay and rear access face
    // the viewer without changing any production geometry.
    translate([dock_w, dock_d, 0]) rotate([0, 0, 180])
        dock_exterior_preview();
}

module dock_v2_back_preview() {
    translate([dock_v2_w, dock_v2_d, 0]) rotate([0, 0, 180])
        dock_v2_exterior_preview();
}

module uno_left_preview() {
    translate([uno_case_d, 0, 0]) rotate([0, 0, 90])
        uno_exterior_preview();
}

module uno_right_preview() {
    translate([0, uno_case_w, 0]) rotate([0, 0, -90])
        uno_exterior_preview();
}

module dock_left_preview() {
    translate([dock_d, 0, 0]) rotate([0, 0, 90])
        dock_exterior_preview();
}

module dock_right_preview() {
    translate([0, dock_w, 0]) rotate([0, 0, -90])
        dock_exterior_preview();
}

module dock_v2_left_preview() {
    translate([dock_v2_d, 0, 0]) rotate([0, 0, 90])
        dock_v2_exterior_preview();
}

module dock_v2_right_preview() {
    translate([0, dock_v2_w, 0]) rotate([0, 0, -90])
        dock_v2_exterior_preview();
}

module uno_exploded_preview() {
    // Separate every user-installed layer while keeping its assembled X/Y
    // position obvious: base, UNO Q, lid, Matrix bezel, then the three-colour
    // hand/target emblem.
    lid_top_z = 60;
    color("#20242a") uno_base();
    translate([0, 0, 17]) board_proxy([uno_x, uno_y]);
    color([0.16, 0.18, 0.20, 0.92])
        translate([0, uno_case_d, lid_top_z]) rotate([180, 0, 0]) uno_lid();
    color("#00b9d8")
        translate([uno_x + 25.75, uno_y + 4.75, lid_top_z + 7])
            matrix_bezel();
    translate([(uno_case_w - 18) / 2, 54.25, 0]) {
        color("#111722") translate([0, 0, lid_top_z + 11]) lid_logo_backing();
        color("#00d6ef") translate([0, 0, lid_top_z + 15]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, lid_top_z + 19]) lid_logo_red();
    }
}

module dock_exploded_preview() {
    // The hub and UNO Q float independently above their cradles so the Dock's
    // two-device layout and open service bay remain easy to understand.
    lid_top_z = 94;
    hub_explode_x = 38;
    color("#20242a") dock_base();
    translate([0, 0, 18]) board_proxy([dock_uno_x, dock_uno_y]);
    color("#59616b") translate([hub_x + hub_explode_x, hub_y, hub_bottom + 30])
        cube([hub_l, hub_w, hub_h]);
    // Suggest the accessible connector bank without tying the printable model
    // to one cosmetic revision of the Arduino hub.
    color("#c8ccd1")
        for (x = [hub_x + hub_explode_x + 13, hub_x + hub_explode_x + 39,
                  hub_x + hub_explode_x + 65, hub_x + hub_explode_x + 91])
            translate([x, hub_y - 0.8, hub_bottom + 34]) cube([15, 1.0, 6]);
    color([0.16, 0.18, 0.20, 0.92])
        translate([0, dock_d, lid_top_z]) rotate([180, 0, 0]) dock_lid();
    color("#00b9d8")
        translate([dock_uno_x + 25.75, dock_uno_y + 4.75, lid_top_z + 7])
            matrix_bezel();
    translate([(dock_w - 18) / 2, 44.25, 0]) {
        color("#111722") translate([0, 0, lid_top_z + 11]) lid_logo_backing();
        color("#00d6ef") translate([0, 0, lid_top_z + 15]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, lid_top_z + 19]) lid_logo_red();
    }
}

module dock_v2_exploded_preview() {
    // The hub remains below the closed lid. It is lifted here only to show the
    // cradle, rear-facing bank, and internal cable-routing space.
    lid_top_z = 104;
    color("#20242a") dock_v2_base();
    translate([0, 0, 22]) board_proxy([dock_v2_uno_x, dock_v2_uno_y]);
    translate([0, 0, 42]) hub_proxy_v2();
    color([0.16, 0.18, 0.20, 0.92])
        translate([0, dock_v2_d, lid_top_z]) rotate([180, 0, 0]) dock_v2_lid();
    color("#00b9d8")
        translate([dock_v2_uno_x + 25.75, dock_v2_uno_y + 4.75,
                   lid_top_z + 7])
            matrix_bezel();
    translate([(dock_v2_w - 18) / 2, 44.25, 0]) {
        color("#111722") translate([0, 0, lid_top_z + 11]) lid_logo_backing();
        color("#00d6ef") translate([0, 0, lid_top_z + 15]) lid_logo_cyan();
        color("#ff2145") translate([0, 0, lid_top_z + 19]) lid_logo_red();
    }
}

if (part == "uno_base") uno_base();
else if (part == "uno_lid") uno_lid();
else if (part == "uno_lid_full_logo") uno_lid(true);
else if (part == "dock_base") dock_base();
else if (part == "dock_lid") dock_lid();
else if (part == "dock_lid_full_logo") dock_lid(true);
else if (part == "dock_v2_base") dock_v2_base();
else if (part == "dock_v2_lid") dock_v2_lid();
else if (part == "dock_v2_lid_full_logo") dock_v2_lid(true);
else if (part == "matrix_bezel") matrix_bezel();
else if (part == "lid_logo_backing") lid_logo_backing();
else if (part == "lid_logo_cyan") lid_logo_cyan();
else if (part == "lid_logo_red") lid_logo_red();
else if (part == "target_badge_backing") target_badge_backing();
else if (part == "target_badge_cyan") target_badge_cyan();
else if (part == "target_badge_red") target_badge_red();
else if (part == "target_badge_multicolor") target_badge_multicolor();
else if (part == "full_logo_backing") full_logo_backing();
else if (part == "full_logo_cyan") full_logo_cyan();
else if (part == "full_logo_red") full_logo_red();
else if (part == "full_logo_multicolor") full_logo_multicolor();
else if (part == "compact_full_logo_backing") compact_full_logo_backing();
else if (part == "compact_full_logo_cyan") compact_full_logo_cyan();
else if (part == "compact_full_logo_red") compact_full_logo_red();
else if (part == "compact_full_logo_multicolor") compact_full_logo_multicolor();
else if (part == "lid_logo_multicolor") lid_logo_multicolor();
else if (part == "branding_preview") branding_preview();
else if (part == "branding_insets_preview") branding_insets_preview();
else if (part == "lid_logo_options_preview") lid_logo_options_preview();
else if (part == "uno_lid_logo_options_preview") uno_lid_logo_options_preview();
else if (part == "usb_c_coupon") usb_c_fit_coupon();
else if (part == "hub_coupon") hub_fit_coupon();
else if (part == "dock_preview") dock_preview();
else if (part == "dock_v2_preview") dock_v2_preview();
else if (part == "uno_exterior_preview") uno_exterior_preview();
else if (part == "dock_exterior_preview") dock_exterior_preview();
else if (part == "dock_v2_exterior_preview") dock_v2_exterior_preview();
else if (part == "dock_v2_port_access_preview") dock_v2_port_access_preview();
else if (part == "uno_back_preview") uno_back_preview();
else if (part == "dock_back_preview") dock_back_preview();
else if (part == "dock_v2_back_preview") dock_v2_back_preview();
else if (part == "uno_left_preview") uno_left_preview();
else if (part == "uno_right_preview") uno_right_preview();
else if (part == "dock_left_preview") dock_left_preview();
else if (part == "dock_right_preview") dock_right_preview();
else if (part == "dock_v2_left_preview") dock_v2_left_preview();
else if (part == "dock_v2_right_preview") dock_v2_right_preview();
else if (part == "uno_exploded_preview") uno_exploded_preview();
else if (part == "dock_exploded_preview") dock_exploded_preview();
else if (part == "dock_v2_exploded_preview") dock_v2_exploded_preview();
else assembly_preview();
