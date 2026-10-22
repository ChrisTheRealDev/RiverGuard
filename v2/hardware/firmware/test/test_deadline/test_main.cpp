#include "retry_deadline.h"
static_assert(deadlineReady(false, 0U, 0U), "unscheduled at boot");
static_assert(deadlineReady(false, 0x80000000U, 0U), "unscheduled after signed boundary");
static_assert(deadlineReady(false, 0xffffffffU, 0U), "unscheduled before rollover");
static_assert(!deadlineReady(true, 0x7fffffffU, 0x80000001U), "wait across signed boundary");
static_assert(deadlineReady(true, 0x80000001U, 0x80000001U), "ready at signed boundary deadline");
static_assert(!deadlineReady(true, 0xfffffffeU, 2U), "wait across rollover");
static_assert(!deadlineReady(true, 1U, 2U), "still waiting after rollover");
static_assert(deadlineReady(true, 2U, 2U), "ready after rollover");
static_assert(deadlineReady(true, 3U, 2U), "ready one millisecond late");
static_assert(!deadlineReady(true, 0xffffffffU, 0U), "scheduled zero is not an unset sentinel");
static_assert(deadlineReady(true, 0U, 0U), "scheduled zero becomes ready at rollover");
