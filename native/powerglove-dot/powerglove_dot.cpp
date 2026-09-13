// Project: VirtualGlove
// File: native/powerglove-dot/powerglove_dot.cpp
// Purpose: Display the receiver's latest native X/Y sample as a calibration dot.
// Author: Iain Bennett
// Copyright (c) 2026 Iain Bennett
// SPDX-License-Identifier: MIT
// Change log:
//   2026-09-09 - Added the ROM-free RetroPie calibration test.
// Full history: docs/CHANGELOG.md and Git history.

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fcntl.h>
#include <unistd.h>

extern "C" {
typedef bool (*retro_environment_t)(unsigned, void*);
typedef void (*retro_video_refresh_t)(const void*, unsigned, unsigned, size_t);
typedef void (*retro_audio_sample_t)(int16_t, int16_t);
typedef size_t (*retro_audio_sample_batch_t)(const int16_t*, size_t);
typedef void (*retro_input_poll_t)(void);
typedef int16_t (*retro_input_state_t)(unsigned, unsigned, unsigned, unsigned);
struct retro_game_info { const char* path; const void* data; size_t size; const char* meta; };
struct retro_system_info { const char* library_name; const char* library_version; const char* valid_extensions; bool need_fullpath; bool block_extract; };
struct retro_game_geometry { unsigned base_width, base_height, max_width, max_height; float aspect_ratio; };
struct retro_system_timing { double fps, sample_rate; };
struct retro_system_av_info { retro_game_geometry geometry; retro_system_timing timing; };
}

namespace {
constexpr unsigned WIDTH = 256, HEIGHT = 224;
constexpr unsigned RETRO_API_VERSION = 1;
constexpr unsigned RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10;
constexpr unsigned RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18;
constexpr unsigned RETRO_PIXEL_FORMAT_XRGB8888 = 1;
constexpr uint8_t FLAG_DETECTED = 1, FLAG_CALIBRATED = 2;
constexpr uint8_t PROFILE_SUPER_GLOVE_BALL = 1;
constexpr uint64_t STALE_NS = 250000000ULL;
uint32_t frame[WIDTH * HEIGHT];
retro_environment_t environment_cb = nullptr;
retro_video_refresh_t video_cb = nullptr;

uint16_t le16(const uint8_t* p) { return uint16_t(p[0]) | (uint16_t(p[1]) << 8); }
uint32_t le32(const uint8_t* p) { return uint32_t(le16(p)) | (uint32_t(le16(p + 2)) << 16); }
uint64_t le64(const uint8_t* p) { return uint64_t(le32(p)) | (uint64_t(le32(p + 4)) << 32); }
int16_t signed16(const uint8_t* p) { return static_cast<int16_t>(le16(p)); }

uint64_t now_ns() {
  timespec value{};
  return clock_gettime(CLOCK_MONOTONIC, &value) == 0
      ? uint64_t(value.tv_sec) * 1000000000ULL + uint64_t(value.tv_nsec) : 0;
}

bool sample(int16_t& x, int16_t& y) {
  const char* configured = std::getenv("VIRTUALGLOVE_NATIVE_STATE");
  const char* path = configured && *configured ? configured : "/run/virtualglove/native-state";
  const int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) return false;
  uint8_t data[64];
  const ssize_t count = pread(fd, data, sizeof(data), 0);
  close(fd);
  if (count != 64 || std::memcmp(data, "PGV1", 4) != 0 || le16(data + 4) != 1
      || le16(data + 6) != 64) return false;
  const uint32_t first_guard = le32(data + 8), last_guard = le32(data + 60);
  const uint64_t arrived = le64(data + 16), now = now_ns();
  if ((first_guard & 1U) || first_guard != last_guard || !now || arrived > now
      || now - arrived > STALE_NS || (data[32] & (FLAG_DETECTED | FLAG_CALIBRATED))
      != (FLAG_DETECTED | FLAG_CALIBRATED) || data[38] != PROFILE_SUPER_GLOVE_BALL) return false;
  x = signed16(data + 24); y = signed16(data + 26);
  return true;
}

void pixel(int x, int y, uint32_t colour) {
  if (x >= 0 && y >= 0 && x < int(WIDTH) && y < int(HEIGHT)) frame[y * WIDTH + x] = colour;
}

void line(int x0, int y0, int x1, int y1, uint32_t colour) {
  const int dx = std::abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
  const int dy = -std::abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
  int error = dx + dy;
  for (;;) {
    pixel(x0, y0, colour);
    if (x0 == x1 && y0 == y1) break;
    const int twice = 2 * error;
    if (twice >= dy) { error += dy; x0 += sx; }
    if (twice <= dx) { error += dx; y0 += sy; }
  }
}

void render() {
  std::fill(frame, frame + WIDTH * HEIGHT, 0x00101820U);
  line(16, HEIGHT / 2, WIDTH - 17, HEIGHT / 2, 0x00233d48U);
  line(WIDTH / 2, 24, WIDTH / 2, HEIGHT - 18, 0x00233d48U);
  int16_t x = 0, y = 0;
  if (sample(x, y)) {
    const int px = 16 + int((int64_t(x) + 32767) * (WIDTH - 33) / 65534);
    const int py = 24 + int((int64_t(y) + 32767) * (HEIGHT - 43) / 65534);
    for (int dy = -5; dy <= 5; ++dy)
      for (int dx = -5; dx <= 5; ++dx)
        if (dx * dx + dy * dy <= 25) pixel(px + dx, py + dy, 0x00ffd43bU);
    for (unsigned row = 4; row < 10; ++row)
      for (unsigned column = 4; column < 22; ++column) frame[row * WIDTH + column] = 0x003bd671U;
  } else {
    line(WIDTH / 2 - 8, HEIGHT / 2 - 8, WIDTH / 2 + 8, HEIGHT / 2 + 8, 0x00e04b4bU);
    line(WIDTH / 2 + 8, HEIGHT / 2 - 8, WIDTH / 2 - 8, HEIGHT / 2 + 8, 0x00e04b4bU);
  }
  if (video_cb) video_cb(frame, WIDTH, HEIGHT, WIDTH * sizeof(uint32_t));
}
}

extern "C" {
void retro_set_environment(retro_environment_t cb) { environment_cb = cb; bool yes = true; cb(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &yes); }
void retro_set_video_refresh(retro_video_refresh_t cb) { video_cb = cb; }
void retro_set_audio_sample(retro_audio_sample_t) {}
void retro_set_audio_sample_batch(retro_audio_sample_batch_t) {}
void retro_set_input_poll(retro_input_poll_t) {}
void retro_set_input_state(retro_input_state_t) {}
unsigned retro_api_version() { return RETRO_API_VERSION; }
void retro_init() { unsigned format = RETRO_PIXEL_FORMAT_XRGB8888; if (environment_cb) environment_cb(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format); }
void retro_deinit() {}
void retro_get_system_info(retro_system_info* info) { *info = {"VirtualGlove Calibration Test", "1.0", "", false, false}; }
void retro_get_system_av_info(retro_system_av_info* info) { *info = {{WIDTH, HEIGHT, WIDTH, HEIGHT, 4.0f / 3.0f}, {60.0988, 48000.0}}; }
void retro_set_controller_port_device(unsigned, unsigned) {}
void retro_reset() {}
void retro_run() { render(); }
size_t retro_serialize_size() { return 0; }
bool retro_serialize(void*, size_t) { return false; }
bool retro_unserialize(const void*, size_t) { return false; }
void retro_cheat_reset() {}
void retro_cheat_set(unsigned, bool, const char*) {}
bool retro_load_game(const retro_game_info*) { return true; }
bool retro_load_game_special(unsigned, const retro_game_info*, size_t) { return false; }
void retro_unload_game() {}
unsigned retro_get_region() { return 0; }
void* retro_get_memory_data(unsigned) { return nullptr; }
size_t retro_get_memory_size(unsigned) { return 0; }
}
