/* Project: VirtualGlove
 * File: native/nestopia-powerglove/diagnostic_trace.h
 * Purpose: Buffer opt-in core consumption timestamps; export only after unload.
 * Author: Iain Bennett
 * Copyright (c) 2026 Iain Bennett
 * SPDX-License-Identifier: MIT
 * Change log:
 *   2026-09-06 - Add a separate diagnostic build without changing the native ABI.
 * Full history: docs/CHANGELOG.md and Git history.
 */
#ifndef PGV_DIAGNOSTIC_TRACE_H
#define PGV_DIAGNOSTIC_TRACE_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>

struct pgv_diagnostic_event {
   uint64_t published_ns, consumed_ns;
   uint32_t sequence, guard, valid;
};
static pgv_diagnostic_event *pgv_diagnostic_events = NULL;
static unsigned pgv_diagnostic_count = 0, pgv_diagnostic_dropped = 0;
static int pgv_diagnostic_fd = -1;
static uint64_t pgv_diagnostic_deadline = 0;
static const unsigned PGV_DIAGNOSTIC_CAPACITY = 20000;

static uint64_t pgv_diagnostic_now(void) {
   struct timespec value;
   return clock_gettime(CLOCK_MONOTONIC, &value) == 0
      ? (uint64_t)value.tv_sec * 1000000000ULL + value.tv_nsec : 0;
}
static void pgv_diagnostic_open(void) {
   const char *path = getenv("VIRTUALGLOVE_CORE_DIAGNOSTIC_TRACE");
   if (!path || !*path || pgv_diagnostic_fd >= 0) return;
   const char *duration = getenv("VIRTUALGLOVE_DIAGNOSTIC_SECONDS");
   char *end = NULL;
   const double seconds = duration ? strtod(duration, &end) : 180.0;
   if (!(seconds >= 1 && seconds <= 600) || (duration && (!end || *end))) return;
   pgv_diagnostic_fd = open(path, O_WRONLY | O_CREAT | O_EXCL, 0600);
   if (pgv_diagnostic_fd < 0) return;
   pgv_diagnostic_events = (pgv_diagnostic_event*)calloc(
      PGV_DIAGNOSTIC_CAPACITY, sizeof(pgv_diagnostic_event));
   if (!pgv_diagnostic_events) {
      close(pgv_diagnostic_fd); pgv_diagnostic_fd = -1; return;
   }
   pgv_diagnostic_count = pgv_diagnostic_dropped = 0;
   pgv_diagnostic_deadline = pgv_diagnostic_now() + (uint64_t)(seconds * 1e9);
}
static void pgv_diagnostic_record(bool valid, uint32_t sequence,
      uint32_t guard, uint64_t published_ns) {
   if (!pgv_diagnostic_events) return;
   const uint64_t now = pgv_diagnostic_now();
   if (!now || now > pgv_diagnostic_deadline) return;
   if (pgv_diagnostic_count == PGV_DIAGNOSTIC_CAPACITY) {
      ++pgv_diagnostic_dropped; return;
   }
   pgv_diagnostic_event &event = pgv_diagnostic_events[pgv_diagnostic_count++];
   event.valid = valid; event.sequence = sequence; event.guard = guard;
   event.published_ns = published_ns; event.consumed_ns = now;
}
static void pgv_diagnostic_close(void) {
   if (pgv_diagnostic_fd < 0) return;
   FILE *stream = fdopen(pgv_diagnostic_fd, "w");
   if (stream) {
      fprintf(stream, "valid,sequence,guard,published_ns,consumed_ns\n");
      for (unsigned i = 0; i < pgv_diagnostic_count; ++i) {
         const pgv_diagnostic_event &event = pgv_diagnostic_events[i];
         fprintf(stream, "%u,%u,%u,%llu,%llu\n", event.valid, event.sequence,
            event.guard, (unsigned long long)event.published_ns,
            (unsigned long long)event.consumed_ns);
      }
      fprintf(stream, "# dropped=%u\n", pgv_diagnostic_dropped);
      fclose(stream);
   } else close(pgv_diagnostic_fd);
   free(pgv_diagnostic_events); pgv_diagnostic_events = NULL;
   pgv_diagnostic_fd = -1;
}
#endif
