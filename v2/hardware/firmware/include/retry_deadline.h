#pragma once
#include <stdint.h>
// A zero deadline is a valid wrapped time, never an implicit unscheduled marker.
// Intervals are bounded to < 2^31 milliseconds by the network retry policy.
constexpr bool deadlineReady(bool scheduled, uint32_t now, uint32_t deadline) {
  return !scheduled || static_cast<int32_t>(now - deadline) >= 0;
}
