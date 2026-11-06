/* SPDX-License-Identifier: GPL-2.0-only
 * Portable odin ST -> HID report adapter. OS/IOHIDDevice integration is separate.
 */
#ifndef ODIN_ST_HID_BRIDGE_H
#define ODIN_ST_HID_BRIDGE_H
#include "odin_st_touch_core.h"

#define ODIN_HID_REPORT_BYTES 62u
#define ODIN_HID_BATCH_FRAMES (ODIN_ST_FIFO_EVENTS + 1u)
enum { ODIN_HID_OK = 0, ODIN_HID_SCAN_RESTART = 1,
       ODIN_HID_SENSOR_ERROR = -1, ODIN_HID_SEND_ERROR = -2 };

struct odin_hid_snapshot {
    uint16_t active;
    uint16_t x[ODIN_ST_CONTACTS], y[ODIN_ST_CONTACTS];
};
struct odin_hid_io {
    void *bus_context;
    bool (*transfer)(void *, const uint8_t *, unsigned, uint8_t *, unsigned);
    void *report_context;
    /* Return true ONLY after this report is accepted. Serial, non-reentrant
     * worker; caller owns lifecycle, locks, timing and IOHIDDevice ABI checks.
     * Failure retries the saved report, never a consumed controller FIFO read.
     */
    bool (*send_report)(void *, const uint8_t *, unsigned);
};
struct odin_hid_bridge {
    struct odin_st_state core;
    struct odin_hid_io io;
    struct odin_hid_snapshot acknowledged, working;
    struct odin_hid_snapshot frames[ODIN_HID_BATCH_FRAMES];
    uint16_t pending_live, pending_up;
    unsigned queued, cursor;
    int batch_result;
    bool dirty, overflow;
    uint32_t accepted_reports, failed_sends;
};

#ifdef __cplusplus
extern "C" {
#endif
void odin_hid_init(struct odin_hid_bridge *, struct odin_hid_io);
bool odin_hid_identify(struct odin_hid_bridge *, uint8_t id[2]);
bool odin_hid_start_scan(struct odin_hid_bridge *);
/* Flush saved HID frames first, or consume exactly one FIFO batch. Never call
 * concurrently or from the HID report callback. READY requires explicit scan
 * restart by the worker; IC errors require an explicit driver reinitialization.
 */
int odin_hid_poll(struct odin_hid_bridge *);
/* Queue acknowledged tip-ups before stopping hardware or detaching the sink.
 * A failed send remains queued; caller must drain before destroying context.
 */
int odin_hid_release(struct odin_hid_bridge *);
#ifdef __cplusplus
}
#endif
#endif
