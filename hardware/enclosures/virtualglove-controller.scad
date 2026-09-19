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
                cylinder(h = uno_standoff_top - floor_t, d = 7.0);
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

module badge_recess(size, y, z_height) {
    translate([(size[0] - 55) / 2, y, -0.1])
        rounded_prism([55, 13, min(0.85, z_height) + 0.1], 2.0);
}

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

module uno_lid() {
    difference() {
        lid_shell([uno_case_w, uno_case_d], 6.0, uno_corner);
        print_face_transform(uno_case_d) {
            matrix_window([uno_x, uno_y], top_t + 0.2);
            badge_recess([uno_case_w, uno_case_d], 57.5, top_t);
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

module dock_lid() {
    difference() {
        lid_shell([dock_w, dock_d], 6.0, dock_corner);
        print_face_transform(dock_d) {
            matrix_window([dock_uno_x, dock_uno_y], top_t + 0.2);
            badge_recess([dock_w, dock_d], 48.0, top_t);
            vent_field([dock_uno_x + 6, dock_uno_y + 31, -0.2, top_t + 0.4],
                       8, 2, 7, 6, 5, 2);
            // Open bay around all hub faces, including Ethernet and cable ends.
            translate([hub_x - 4.0, hub_y - 7.0, -0.2])
                cube([hub_l + 8.0, hub_w + 14.0, top_t + 7]);
        }
    }
}

module matrix_bezel() {
    difference() {
        rounded_prism([33.0, 23.0, 1.2], 2.2);
        translate([1.75, 1.75, -0.1]) cube([29.5, 19.5, 1.4]);
    }
}

module wordmark_badge(width = 54.5) {
    union() {
        rounded_prism([width, 12.5, 0.8], 1.8);
        // A print-safe adaptation of the italic pixel wordmark.  The underline
        // and terminal bars echo the full logo without reproducing screen-only
        // glow, shadows, or sub-nozzle pixels.
        translate([width / 2 - 0.8, 7.0, 0.75])
            linear_extrude(height = 0.9)
                text("VirtualGlove", size = 5.7, halign = "center", valign = "center",
                     font = "Liberation Sans:style=Bold Italic");
        translate([5.0, 2.1, 0.75]) cube([42.5, 1.0, 0.9]);
        for (x = [49.0, 51.1])
            translate([x, 2.1, 0.75]) cube([1.3, 1.0, 0.9]);
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

module target_badge_backing() {
    rounded_prism([28, 28, 0.8], 3.0);
}

module target_badge_cyan() {
    difference() {
        translate([14, 12.0, 0]) scale([0.82, 0.82, 1]) hand_target_mark(0.9);
        translate([2.6, 11.45, -0.1]) cube([22.8, 1.1, 1.1]);
    }
}

module target_badge_red() {
    // The target beam and three terminal pixels are separate for economical
    // ACE Pro colour changes or a glued two-colour assembly.
    translate([2.8, 11.55, 0]) cube([22.4, 0.9, 0.9]);
    for (x = [22.0, 24.0, 26.0])
        translate([x, 10.9, 0]) cube([1.0, 2.2, 0.9]);
}

module full_logo_backing() {
    rounded_prism([100, 30, 0.8], 3.0);
}

module full_logo_cyan() {
    difference() {
        translate([14, 13.0, 0]) scale([0.72, 0.72, 1]) hand_target_mark(0.9);
        translate([4.3, 12.45, -0.1]) cube([20.0, 1.1, 1.1]);
    }
    translate([27, 17.0, 0])
        linear_extrude(height = 0.9)
            text("VirtualGlove", size = 7.7, valign = "center",
                 font = "Liberation Sans:style=Bold Italic");
    translate([28, 8.0, 0]) cube([55, 1.3, 0.9]);
}

module full_logo_red() {
    translate([4.5, 12.55, 0]) cube([19, 0.9, 0.9]);
    for (x = [86, 89, 92])
        translate([x, 7.5, 0]) cube([1.8, 2.2, 0.9]);
}

module branding_preview() {
    color("#111722") full_logo_backing();
    color("#00d6ef") translate([0, 0, 0.8]) full_logo_cyan();
    color("#ff2145") translate([0, 0, 0.8]) full_logo_red();
    translate([106, 1, 0]) {
        color("#111722") target_badge_backing();
        color("#00d6ef") translate([0, 0, 0.8]) target_badge_cyan();
        color("#ff2145") translate([0, 0, 0.8]) target_badge_red();
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

module uno_exterior_preview() {
    color("#20242a") uno_base();
    color("#2a2d33")
        translate([0, uno_case_d, uno_base_h + top_t]) rotate([180, 0, 0]) uno_lid();
    color("#00b9d8")
        translate([uno_x + 25.75, uno_y + 4.75, uno_base_h + top_t + 0.05])
            matrix_bezel();
    color("#f26a21")
        translate([(uno_case_w - 54.5) / 2, 57.75, uno_base_h + top_t - 0.8])
            wordmark_badge();
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
    color("#f26a21")
        translate([(dock_w - 54.5) / 2, 48.25, dock_base_h + top_t - 0.8])
            wordmark_badge();
}

if (part == "uno_base") uno_base();
else if (part == "uno_lid") uno_lid();
else if (part == "dock_base") dock_base();
else if (part == "dock_lid") dock_lid();
else if (part == "matrix_bezel") matrix_bezel();
else if (part == "badge") wordmark_badge();
else if (part == "target_badge_backing") target_badge_backing();
else if (part == "target_badge_cyan") target_badge_cyan();
else if (part == "target_badge_red") target_badge_red();
else if (part == "full_logo_backing") full_logo_backing();
else if (part == "full_logo_cyan") full_logo_cyan();
else if (part == "full_logo_red") full_logo_red();
else if (part == "branding_preview") branding_preview();
else if (part == "usb_c_coupon") usb_c_fit_coupon();
else if (part == "hub_coupon") hub_fit_coupon();
else if (part == "dock_preview") dock_preview();
else if (part == "uno_exterior_preview") uno_exterior_preview();
else if (part == "dock_exterior_preview") dock_exterior_preview();
else assembly_preview();
