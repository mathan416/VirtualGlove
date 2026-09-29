// Controller Router owns the UNO Q Matrix. Product apps submit validated frames
// through its Linux service; neither app needs to replace this sketch.
#include "Arduino_RouterBridge.h"
#include <Arduino_LED_Matrix.h>
#include <zephyr/kernel.h>

Arduino_LED_Matrix matrix;
volatile unsigned long lastFrameAt = 0;
volatile unsigned long nextIdleAt = 0;
volatile unsigned int idleFrame = 0;
volatile bool startupComplete = false;
unsigned int loadingFrame = 0;
struct k_thread displayThread;
k_thread_stack_t* displayStack = nullptr;
k_tid_t displayThreadId = nullptr;

void drawIdle() {
  uint8_t pixels[104] = {};
  const uint8_t r[7] = {30, 17, 17, 30, 20, 18, 17};
  const uint8_t dot[4] = {4, 5, 6, 5};
  for (int y = 0; y < 7; ++y) {
    for (int x = 0; x < 5; ++x) {
      if (r[y] & (1 << (4 - x))) pixels[y * 13 + x + 4] = 4;
    }
  }
  pixels[7 * 13 + dot[idleFrame++ % 4] + 2] = 7;
  matrix.draw(pixels);
}

// Keep the loading display alive before Linux and Router's host service start.
void drawLoading() {
  static const char* frames[][8] = {
    {"0007777777000", "0000733370000", "0000073700000", "0000007000000", "0000003000000", "0000070700000", "0000700070000", "0007777777000"},
    {"0007777777000", "0000733370000", "0000073700000", "0000003000000", "0000007000000", "0000070700000", "0000703070000", "0007777777000"},
    {"0007777777000", "0000703070000", "0000073700000", "0000003000000", "0000003000000", "0000073700000", "0000733370000", "0007777777000"},
    {"0005555555000", "0000500050000", "0000050500000", "0000003000000", "0000007000000", "0000053500000", "0000533350000", "0005555555000"},
    {"0007777777000", "0000700070000", "0000070700000", "0000007000000", "0000003000000", "0000073700000", "0000733370000", "0007777777000"},
  };
  uint8_t pixels[104];
  unsigned int frame = loadingFrame++ % 5;
  for (int y = 0; y < 8; ++y)
    for (int x = 0; x < 13; ++x) pixels[y * 13 + x] = frames[frame][y][x] - '0';
  matrix.draw(pixels);
}

bool finish_router_startup() {
  startupComplete = true;
  nextIdleAt = 0;
  return true;
}

bool draw_router_frame(String encoded) {
  if (encoded.length() != 104) return false;
  uint8_t pixels[104];
  for (int i = 0; i < 104; ++i) {
    char value = encoded[i];
    if (value < '0' || value > '7') return false;
    pixels[i] = value - '0';
  }
  matrix.draw(pixels);
  startupComplete = true;
  lastFrameAt = millis();
  return true;
}

String get_router_firmware() {
  return String("controller-router-0.2.0");
}

void refreshDisplay() {
  unsigned long now = millis();
  if ((lastFrameAt == 0 || now - lastFrameAt > 1800) && now >= nextIdleAt) {
    if (startupComplete) drawIdle();
    else drawLoading();
    nextIdleAt = now + 350;
  }
}

void displayTask(void*, void*, void*) {
  while (true) { refreshDisplay(); k_msleep(10); }
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  drawLoading();
  displayStack = k_thread_stack_alloc(2048, 0);
  if (displayStack != nullptr) {
    displayThreadId = k_thread_create(&displayThread, displayStack, 2048,
                                     displayTask, nullptr, nullptr, nullptr, 5, 0, K_NO_WAIT);
    k_thread_name_set(displayThreadId, "controller-router-matrix");
  }
  Bridge.begin();
  Bridge.provide("draw_router_frame", draw_router_frame);
  Bridge.provide("get_router_firmware", get_router_firmware);
  Bridge.provide("finish_router_startup", finish_router_startup);
}

void loop() {
  if (displayThreadId == nullptr) refreshDisplay();
  delay(10);
}
