// Project: VirtualGlove
// File: sketch/sketch.ino
// Purpose: Render protected status, pairing, and gesture-profile feedback on the UNO Q LED matrix.
// Author: Iain Bennett
// Copyright (c) 2026 Iain Bennett
// SPDX-License-Identifier: MIT
// Full history: docs/CHANGELOG.md and Git history.
// Change log:
//   2026-09-06 - Implement approved player and connectivity refinements.
//   2026-09-06 - Add idle-only On, Dim, and connection-pixel attract settings.
//   2026-09-06 - Expose the compiled matrix source fingerprint through Router Bridge.
//   2026-09-06 - Add an idle lightning flash, clearer fingers and cuff, and a softer glow.
//   2026-09-04 - Share the scanning letter animation between Learn and Tune.
//   2026-09-02 - Added to VirtualGlove.
//   2026-09-03 - Standardized source documentation and maintenance metadata.
//   2026-09-03 - Added the gestures-idle Power Glove attract animation.
//   2026-09-03 - Refined the attract animation with cuff travel, spark motion, and grayscale pulsing.
//   2026-09-03 - Added a scanning L animation for Learn mode.

#include "Arduino_RouterBridge.h"
#include <Arduino_LED_Matrix.h>
#include <zephyr/kernel.h>
#include "firmware_version.h"

// App Lab starts this sketch after the UNO Q's protected system-boot display
// has finished. The Python vision process then selects one of these states.
enum PowerGloveStatus {
  PG_OFF = 0,
  PG_LOADING = 1,
  PG_READY = 2,
  PG_TRACKING = 3,
  PG_ERROR = 4,
  PG_PAIRING = 5,
  PG_GESTURES_IDLE = 6,
  PG_LEARNING = 7,
  PG_TUNING = 8,
};

Arduino_LED_Matrix matrix;
volatile int requestedStatus = PG_LOADING;
volatile int requestedProfile = 0;
volatile int requestedAttract = 0; // 0 On, 1 Dim, 2 Off
volatile int requestedConnections = 0;
int drawnAttract = -1;
int drawnConnections = -1;
volatile uint32_t requestedPairingId = 0;
volatile int requestedPairingPin = 0;
int drawnStatus = -1;
int drawnProfile = -1;
unsigned long nextFrameAt = 0;
uint8_t animationFrame = 0;
struct k_thread displayThread;
k_thread_stack_t* displayStack = nullptr;
k_tid_t displayThreadId = nullptr;

// Original 8-bit artwork sized for the UNO Q's 8x13 blue matrix. Characters
// encode brightness: '.' is off, '1' through '7' select exact grayscale
// levels, 'o' is legacy dim, and 'O' is full brightness.
// A distinct hourglass means startup/loading; the glove remains the idle display.
const char* const loadingFrames[][8] = {
  {"...7777777...", "....7ooo7....", ".....7o7.....", "......7......", "......o......", ".....7.7.....", "....7...7....", "...7777777..."},
  {"...7777777...", "....7ooo7....", ".....7o7.....", "......o......", "......7......", ".....7.7.....", "....7.o.7....", "...7777777..."},
  {"...7777777...", "....7.o.7....", ".....7o7.....", "......o......", "......o......", ".....7o7.....", "....7ooo7....", "...7777777..."},
  {"...5555555...", "....5...5....", ".....5.5.....", "......o......", "......7......", ".....5o5.....", "....5ooo5....", "...5555555..."},
  {"...7777777...", "....7...7....", ".....7.7.....", "......7......", "......o......", ".....7o7.....", "....7ooo7....", "...7777777..."},
};

const char* const readyFrame[8] = {
  ".OOOO..OOOOO.",
  ".O...O.O.....",
  ".OOOO..O.OOO.",
  ".O.....O...O.",
  ".O.....O...O.",
  ".O.....OOOOO.",
  ".............",
  ".O.O.O.O.O.O.",
};

const char* const trackingFrames[][8] = {
  {
    ".....OOO.....", "...OOoOOO...", "..OO...OOO...", "..O..O..O....",
    "..OO...OO....", "...OOOOO.....", ".....O.......", "....OOO......",
  },
  {
    ".....ooo.....", "...ooOooo...", "..oo...ooo...", "..o..O..o....",
    "..oo...oo....", "...ooooo.....", ".....O.......", "....ooo......",
  },
};

const char* const errorFrame[8] = {
  ".OO.......OO.", ".oOO.....OOo.", "...OO...OO...", "....OO.OO....",
  ".....OOO.....", "....OO.OO....", "...OO...OO...", ".OO.......OO.",
};

// Pinball-display-inspired glove silhouettes for the healthy gestures-paused
// state. Edge highlighting gives the tiny monochrome image depth without
// saturating the palm into an unreadable rectangle.
const char* const idleOpenGlove[8] = {
  "......#.#....", "....#.#.#.#..", "....#.#.#.#..", ".#..#######..",
  ".##.######...", "..########...", "....####.....", "....####.....",
};

const char* const idleCurlGlove[8] = {
  ".............", ".............", "....#.#.#.#..", ".#..#######..",
  ".##.######...", "..########...", "....####.....", "....####.....",
};

const char* const idleFistGlove[8] = {
  ".............", ".............", "...#######...", "..########...",
  ".#########...", "..########...", "....####.....", "....####.....",
};

// A full-height zigzag silhouette stays readable during the short double flash.
const char* const idleLightning[8] = {
  ".......###...", "......###....", ".....###.....", "....#####....",
  "......##.....", ".....##......", "....##.......", "....#........",
};

// Per-frame timing makes the entrance, finger curl, spark, and outline pulse
// distinct. The final frame holds long enough to serve as a friendly idle icon.
const uint16_t idleFrameDurations[] = {
  120, 90, 160, 100,            // lightning: flash, dim, flash, fade
  80, 90, 110, 150,             // cuff eases into position
  100, 120, 230,                // glove rises, then holds open
  120, 220, 120, 200,           // curl, readable fist hold, reopen
  80, 80, 80, 80, 80, 80, 80, 80, // spark and comet trail
  100, 120, 150, 180, 220, 700, // gradual glow and resting hold
};

// Five-pixel-wide glyphs A-I, B, S, G, and 0-9. Letter programs use a large
// centred glyph, dedicated game profiles display BS/GB, and numeric programs
// use one or two digits.
const uint8_t programGlyphs[9][7] = {
  {14,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
  {14,17,16,16,16,17,14}, {30,17,17,17,17,17,30},
  {31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
  {14,17,16,23,17,17,14}, {17,17,17,31,17,17,17},
  {31,4,4,4,4,4,31},
};
const uint8_t glyphB[7] = {30,17,17,30,17,17,30};
const uint8_t glyphS[7] = {15,16,16,14,1,1,30};
const uint8_t glyphG[7] = {14,17,16,23,17,17,14};
const uint8_t digitGlyphs[10][7] = {
  {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14},
  {14,17,1,2,4,8,31}, {30,1,1,14,1,1,30},
  {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
  {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8},
  {14,17,17,14,17,17,14}, {14,17,17,15,1,1,14},
};
const uint8_t glyphN[7] = {17,25,25,21,19,19,17};
const uint8_t glyphP[7] = {30,17,17,30,16,16,16};
const uint8_t glyphT[7] = {31,4,4,4,4,4,4};
const uint8_t glyphL[7] = {16,16,16,16,16,16,31};

void drawRows(const char* const rows[8]);
void setPixelMax(uint8_t* pixels, int x, int y, uint8_t brightness);

// Blend one five-column glyph into the 8x13 matrix framebuffer.
void placeGlyph(uint8_t* pixels, const uint8_t glyph[7], int left, uint8_t brightness) {
  for (int y = 0; y < 7; ++y) {
    for (int x = 0; x < 5; ++x) {
      if (glyph[y] & (1 << (4 - x))) {
        pixels[y * 13 + left + x] = brightness;
      }
    }
  }
}

// Draw one hexadecimal digit used by the physical certificate identity.
void placeHexGlyph(uint8_t* pixels, uint8_t value, int left) {
  if (value < 10) {
    placeGlyph(pixels, digitGlyphs[value], left, 7);
  } else {
    placeGlyph(pixels, programGlyphs[value - 10], left, 7);
  }
}

// Alternate the certificate identity and one-time PIN during secure pairing.
void drawPairing(uint8_t frame) {
  uint8_t pixels[104] = {0};
  if (frame == 0) {
    placeGlyph(pixels, programGlyphs[8], 1, 7);  // I
    placeGlyph(pixels, programGlyphs[3], 7, 7);  // D
  } else if (frame <= 4) {
    const int first = (frame - 1) * 2;
    if (first < 7) placeHexGlyph(pixels, (requestedPairingId >> ((6 - first) * 4)) & 0xF, 1);
    if (first + 1 < 7) placeHexGlyph(pixels, (requestedPairingId >> ((5 - first) * 4)) & 0xF, 7);
  } else if (frame == 5) {
    placeGlyph(pixels, glyphP, 1, 7);
    placeGlyph(pixels, glyphN, 7, 7);
  } else {
    const int first = (frame - 6) * 2;
    int divisor = 1;
    for (int i = 0; i < 5 - first; ++i) divisor *= 10;
    placeGlyph(pixels, digitGlyphs[(requestedPairingPin / divisor) % 10], 1, 7);
    placeGlyph(pixels, digitGlyphs[(requestedPairingPin / (divisor / 10)) % 10], 7, 7);
  }
  matrix.draw(pixels);
}

// Render a compact program or game-profile identifier.
void drawProfile(int profile, bool pulse) {
  uint8_t pixels[104] = {0};
  const uint8_t brightness = pulse ? 4 : 7;
  if (profile >= 1 && profile <= 9) {
    placeGlyph(pixels, programGlyphs[profile - 1], 4, brightness);
  } else if (profile == 10) {
    placeGlyph(pixels, glyphB, 1, brightness);
    placeGlyph(pixels, glyphS, 7, brightness);
  } else if (profile == 11) {
    placeGlyph(pixels, glyphG, 1, brightness);
    placeGlyph(pixels, glyphB, 7, brightness);
  } else if (profile >= 12 && profile <= 25) {
    const int program = profile - 11;
    if (program < 10) {
      placeGlyph(pixels, digitGlyphs[program], 4, brightness);
    } else {
      placeGlyph(pixels, digitGlyphs[1], 1, brightness);
      placeGlyph(pixels, digitGlyphs[program - 10], 7, brightness);
    }
  } else {
    drawRows(readyFrame);
    return;
  }
  matrix.draw(pixels);
}

// Keep Learn and Tune legible with the same bright scan line and trailing glow.
void drawModeLetter(const uint8_t glyph[7], uint8_t frame) {
  uint8_t pixels[104] = {0};
  placeGlyph(pixels, glyph, 4, 3);
  const int scanRow = frame % 8;
  for (int x = 4; x < 9; ++x) {
    if (scanRow < 7 && (glyph[scanRow] & (1 << (8 - x)))) {
      setPixelMax(pixels, x, scanRow, 7);
    }
    if (scanRow > 0 && scanRow - 1 < 7 &&
        (glyph[scanRow - 1] & (1 << (8 - x)))) {
      setPixelMax(pixels, x, scanRow - 1, 5);
    }
  }
  matrix.draw(pixels);
}

// Convert character-based artwork into matrix brightness values and display it.
void drawRows(const char* const rows[8]) {
  uint8_t pixels[104];
  for (int y = 0; y < 8; ++y) {
    for (int x = 0; x < 13; ++x) {
      const char value = rows[y][x];
      if (value >= '1' && value <= '7') {
        pixels[y * 13 + x] = value - '0';
      } else {
        pixels[y * 13 + x] = value == 'O' ? 7 : (value == 'o' ? 2 : 0);
      }
    }
  }
  matrix.draw(pixels);
}

// Raise one matrix pixel without allowing a dim layer to overwrite a brighter
// outline, spark core, or comet trail.
void setPixelMax(uint8_t* pixels, int x, int y, uint8_t brightness) {
  if (x < 0 || x >= 13 || y < 0 || y >= 8) {
    return;
  }
  const int index = y * 13 + x;
  if (brightness > pixels[index]) {
    pixels[index] = brightness;
  }
}

// Test whether a coordinate belongs to one of the 13x8 glove silhouettes.
bool isGlovePixel(const char* const mask[8], int x, int y) {
  return x >= 0 && x < 13 && y >= 0 && y < 8 && mask[y][x] == '#';
}

// Render a glove with separate body and edge levels. minRow supports the two
// reveal frames that grow the hand upward from the already-positioned cuff.
void drawGlove(
  uint8_t* pixels,
  const char* const mask[8],
  uint8_t bodyBrightness,
  uint8_t edgeBrightness,
  int minRow = 0
) {
  for (int y = minRow; y < 8; ++y) {
    for (int x = 0; x < 13; ++x) {
      if (!isGlovePixel(mask, x, y)) {
        continue;
      }
      const bool edge =
        !isGlovePixel(mask, x - 1, y) || !isGlovePixel(mask, x + 1, y) ||
        !isGlovePixel(mask, x, y - 1) || !isGlovePixel(mask, x, y + 1);
      setPixelMax(pixels, x, y, edge ? edgeBrightness : bodyBrightness);
    }
  }
  // A dim wrist band and two bright buckle pixels anchor every hand pose.
  for (int x = 4; x <= 7; ++x) {
    pixels[6 * 13 + x] = bodyBrightness;
    pixels[7 * 13 + x] = edgeBrightness;
  }
  pixels[6 * 13 + 5] = edgeBrightness;
  pixels[6 * 13 + 6] = edgeBrightness;
}

// Render one complete beat of the gestures-paused attract sequence. Motion is
// intentionally broad: the cuff crosses seven columns, the fingers curl over
// three poses, and the spark uses a bright core plus two-position comet trail.
void drawIdleFrame(uint8_t frame, uint8_t ceiling = 7) {
  uint8_t pixels[104] = {0};

  if (frame < 4) {
    const uint8_t flash[] = {7, 2, 7, 1};
    for (int y = 0; y < 8; ++y) {
      for (int x = 0; x < 13; ++x) {
        if (isGlovePixel(idleLightning, x, y)) {
          setPixelMax(pixels, x, y, flash[frame]);
        }
      }
    }
  } else if (frame < 8) {
    const int cuffX[] = {11, 9, 6, 4};
    const int left = cuffX[frame - 4];
    for (int y = 6; y < 8; ++y) {
      for (int x = left; x < left + 4; ++x) {
        setPixelMax(pixels, x, y, y == 7 || x == left + 1 || x == left + 2 ? 5 : 2);
      }
    }
  } else if (frame < 11) {
    const int revealRows[] = {5, 3, 0};
    drawGlove(pixels, idleOpenGlove, 2, 5, revealRows[frame - 8]);
  } else if (frame == 11 || frame == 13) {
    drawGlove(pixels, idleCurlGlove, 2, 5);
  } else if (frame == 12) {
    drawGlove(pixels, idleFistGlove, 2, 6);
  } else if (frame >= 15 && frame < 23) {
    const int sparkX[] = {4, 5, 5, 5, 6, 7, 8, 10};
    const int sparkY[] = {7, 6, 5, 4, 3, 2, 1, 0};
    const int sparkIndex = frame - 15;
    drawGlove(pixels, idleOpenGlove, 1, 3);
    if (sparkIndex >= 2) {
      setPixelMax(
        pixels, sparkX[sparkIndex - 2], sparkY[sparkIndex - 2], 3
      );
    }
    if (sparkIndex >= 1) {
      setPixelMax(
        pixels, sparkX[sparkIndex - 1], sparkY[sparkIndex - 1], 5
      );
    }
    const int x = sparkX[sparkIndex];
    const int y = sparkY[sparkIndex];
    // Small glints preserve the finger gaps; a full cross obscures the hand.
    if (sparkIndex == 3 || sparkIndex == 7) {
      setPixelMax(pixels, x - 1, y, 4);
      setPixelMax(pixels, x + 1, y, 4);
    }
    setPixelMax(pixels, x, y, 7);
  } else if (frame >= 23) {
    const uint8_t body[] = {1, 2, 3, 2, 1, 1};
    const uint8_t edge[] = {3, 5, 7, 5, 4, 4};
    drawGlove(pixels, idleOpenGlove, body[frame - 23], edge[frame - 23]);
  } else {
    drawGlove(pixels, idleOpenGlove, 2, 5);
  }

  for (int i = 0; i < 104; ++i) {
    pixels[i] = (pixels[i] * ceiling + 6) / 7;
  }
  matrix.draw(pixels);
}

// Router Bridge endpoint: request a bounded status code from the Linux app.
void set_powerglove_status(int status) {
  if (status < PG_OFF || status > PG_TUNING) {
    status = PG_ERROR;
  }
  requestedStatus = status;
}

// Only idle rendering consumes these settings; active mode artwork is unchanged.
int set_powerglove_attract(int mode, int connections) {
  requestedAttract = mode >= 0 && mode <= 2 ? mode : 0;
  requestedConnections = connections & 7;
  return requestedAttract;
}

// Router Bridge endpoint: show the certificate identity and one-time PIN.
void set_powerglove_pairing(int pairingId, int pairingPin) {
  requestedPairingId = (uint32_t)pairingId & 0x0FFFFFFF;
  requestedPairingPin = pairingPin >= 0 && pairingPin <= 999999 ? pairingPin : 0;
  requestedStatus = PG_PAIRING;
}

// Router Bridge endpoint: select the active gesture-profile display.
void set_powerglove_profile(int profile) {
  requestedProfile = (profile >= 0 && profile <= 25) ? profile : 0;
}

// Report the identity compiled into the running microcontroller firmware.
String get_powerglove_firmware() {
  return String(POWERGLOVE_FIRMWARE_ID);
}

// Keep the display alive while Router Bridge initialization waits for Linux.
// This task is the sole framebuffer writer after setup draws its first frame.
void refreshMatrix();
void displayTask(void*, void*, void*) {
  while (true) {
    refreshMatrix();
    k_msleep(5);
  }
}

// Initialize visible startup feedback before any blocking bridge calls.
void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  drawRows(loadingFrames[0]);
  displayStack = k_thread_stack_alloc(2048, 0);
  if (displayStack != nullptr) {
    displayThreadId = k_thread_create(&displayThread, displayStack, 2048,
                                    displayTask, nullptr, nullptr, nullptr,
                                    5, 0, K_NO_WAIT);
    k_thread_name_set(displayThreadId, "powerglove-matrix");
  }

  Bridge.begin();
  Bridge.provide("set_powerglove_status", set_powerglove_status);
  Bridge.provide("set_powerglove_profile", set_powerglove_profile);
  Bridge.provide("set_powerglove_pairing", set_powerglove_pairing);
  Bridge.provide("get_powerglove_firmware", get_powerglove_firmware);
  Bridge.provide("set_powerglove_attract", set_powerglove_attract);
}

// Refresh animations only when their frame or requested state changes.
void refreshMatrix() {
  const int status = requestedStatus;
  const int profile = requestedProfile;
  const unsigned long now = millis();

  const int attract = requestedAttract;
  const int connections = requestedConnections;
  if (status == PG_GESTURES_IDLE && (attract != drawnAttract || connections != drawnConnections)) {
    drawnAttract = attract;
    drawnConnections = connections;
    nextFrameAt = 0;
  }

  if (status != drawnStatus || profile != drawnProfile) {
    drawnStatus = status;
    drawnProfile = profile;
    animationFrame = 0;
    nextFrameAt = 0;
    if (status == PG_OFF) {
      matrix.clear();
    } else if (status == PG_READY) {
      drawProfile(profile, false);
    }
  }

  if (now < nextFrameAt) {
    return;
  }

  if (status == PG_LOADING) {
    drawRows(loadingFrames[animationFrame]);
    animationFrame = (animationFrame + 1) % 5;
    nextFrameAt = now + 220;
  } else if (status == PG_TRACKING) {
    if (profile == 0) {
      drawRows(trackingFrames[animationFrame]);
    } else {
      drawProfile(profile, animationFrame != 0);
    }
    animationFrame = (animationFrame + 1) % 2;
    nextFrameAt = now + 360;
  } else if (status == PG_ERROR) {
    if (animationFrame == 0) {
      drawRows(errorFrame);
    } else {
      matrix.clear();
    }
    animationFrame = (animationFrame + 1) % 2;
    nextFrameAt = now + 420;
  } else if (status == PG_PAIRING) {
    drawPairing(animationFrame);
    animationFrame = (animationFrame + 1) % 9;
    nextFrameAt = now + 650;
  } else if (status == PG_GESTURES_IDLE) {
    if (attract == 2) {
      uint8_t pixels[104] = {};
      pixels[7 * 13] = 1; // App running.
      pixels[7 * 13 + 2] = (connections & 1) ? 1 : 0;
      pixels[7 * 13 + 4] = (connections & 2) ? 1 : 0;
      pixels[7 * 13 + 6] = (connections & 4) ? 1 : 0;
      matrix.draw(pixels);
      nextFrameAt = now + 1000;
      return;
    }
    drawIdleFrame(animationFrame, attract == 1 ? 2 : 7);
    nextFrameAt = now + idleFrameDurations[animationFrame];
    animationFrame = (animationFrame + 1) %
      (sizeof(idleFrameDurations) / sizeof(idleFrameDurations[0]));
  } else if (status == PG_LEARNING || status == PG_TUNING) {
    drawModeLetter(status == PG_LEARNING ? glyphL : glyphT, animationFrame);
    animationFrame = (animationFrame + 1) % 8;
    nextFrameAt = now + 160;
  }
}

// Fall back to loop-driven animation if the optional display stack was unavailable.
void loop() {
  if (displayThreadId == nullptr) {
    refreshMatrix();
  }
  delay(5);
}
