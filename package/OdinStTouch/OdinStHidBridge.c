/* SPDX-License-Identifier: GPL-2.0-only */
#include "OdinStHidBridge.h"

static uint16_t axis(uint32_t normalized) {
    /* Core already maps raw odin 0..10799/23999 to 0..65535. Convert once
     * to the descriptor's 0..32767 domain; do not apply sheng's raw extents.
     */
    return (uint16_t)((normalized * 32767u + 32767u) / 65535u);
}

static bool transfer(void *context, const uint8_t *tx, unsigned nt,
                     uint8_t *rx, unsigned nr) {
    struct odin_hid_bridge *b = context;
    return b->io.transfer && b->io.transfer(b->io.bus_context, tx, nt, rx, nr);
}

static void stage(struct odin_hid_bridge *b) {
    if (!b->dirty) return;
    if (b->queued == ODIN_HID_BATCH_FRAMES) { b->overflow = true; return; }
    b->frames[b->queued++] = b->working;
    b->dirty = false;
    b->pending_live = b->pending_up = 0;
}

static void event(void *context, unsigned action, unsigned id,
                  uint32_t x, uint32_t y) {
    struct odin_hid_bridge *b = context;
    const uint16_t bit = (uint16_t)(1u << id);
    /* Merge movement within a complete FIFO batch, but never merge away a
     * short tap or a same-ID release/repress. No HID call while parsing SPI.
     */
    /* Deliver the latest movement before a lift too: dropping it would end
     * a drag at its previously acknowledged position. */
    if ((action == ODIN_ST_UP && b->pending_live) ||
        (action == ODIN_ST_DOWN && (b->pending_up & bit))) stage(b);
    b->working.x[id] = axis(x);
    b->working.y[id] = axis(y);
    if (action == ODIN_ST_UP) {
        b->working.active &= (uint16_t)~bit;
        b->pending_up |= bit;
    } else {
        b->working.active |= bit;
        b->pending_live |= bit;
    }
    b->dirty = true;
}

static void put_contact(uint8_t *p, unsigned flags, unsigned id,
                        const struct odin_hid_snapshot *s) {
    p[0] = (uint8_t)flags; p[1] = (uint8_t)id;
    p[2] = (uint8_t)s->x[id]; p[3] = (uint8_t)(s->x[id] >> 8);
    p[4] = (uint8_t)s->y[id]; p[5] = (uint8_t)(s->y[id] >> 8);
}

static int drain(struct odin_hid_bridge *b) {
    while (b->cursor < b->queued) {
        uint8_t report[ODIN_HID_REPORT_BYTES] = {3};
        const struct odin_hid_snapshot *next = &b->frames[b->cursor];
        unsigned slot = 0;
        for (unsigned id = 0; id < ODIN_ST_CONTACTS; id++) {
            const uint16_t bit = (uint16_t)(1u << id);
            if (next->active & bit) {
                put_contact(report + 1 + slot++ * 6, 3, id, next);
            } else if (b->acknowledged.active & bit) {
                put_contact(report + 1 + slot++ * 6, 2, id, &b->acknowledged);
            }
        }
        /* IDs are the fixed hardware slots 0..9. Their union fits ten slots,
         * including all explicit releases, even when every contact changes.
         */
        report[ODIN_HID_REPORT_BYTES - 1] = (uint8_t)slot;
        if (slot && (!b->io.send_report ||
                     !b->io.send_report(b->io.report_context, report, sizeof report))) {
            b->failed_sends++;
            return ODIN_HID_SEND_ERROR;
        }
        b->acknowledged = *next;
        b->cursor++;
        if (slot) b->accepted_reports++;
    }
    b->queued = b->cursor = 0;
    return b->batch_result;
}

void odin_hid_init(struct odin_hid_bridge *b, struct odin_hid_io io) {
    *b = (struct odin_hid_bridge){0};
    b->io = io;
    const struct odin_st_bus bus = {b, transfer, event};
    odin_st_init(&b->core, bus);
}

bool odin_hid_identify(struct odin_hid_bridge *b, uint8_t id[2]) {
    return !b->queued && odin_st_identify(&b->core, id);
}

bool odin_hid_start_scan(struct odin_hid_bridge *b) {
    if (b->queued || !odin_st_enable_scan(&b->core)) return false;
    b->core.scan_restart_needed = false;
    return true;
}

static void discard_and_release(struct odin_hid_bridge *b) {
    /* Do not publish partial/corrupt batches, even if a transient down had
     * been staged. Release the last acknowledged state instead.
     */
    b->queued = b->cursor = 0;
    b->working = b->acknowledged;
    b->working.active = 0;
    b->pending_live = b->pending_up = 0;
    b->dirty = b->acknowledged.active != 0;
    stage(b);
}

int odin_hid_poll(struct odin_hid_bridge *b) {
    if (b->queued) return drain(b);
    if (b->core.scan_restart_needed) return ODIN_HID_SCAN_RESTART;
    b->working = b->acknowledged;
    b->dirty = b->overflow = false;
    b->pending_live = b->pending_up = 0;
    const bool ok = odin_st_poll(&b->core);
    b->batch_result = !ok || b->overflow ? ODIN_HID_SENSOR_ERROR :
        b->core.scan_restart_needed ? ODIN_HID_SCAN_RESTART : ODIN_HID_OK;
    if (b->batch_result != ODIN_HID_OK) {
        odin_st_release_all(&b->core);
        discard_and_release(b);
    } else stage(b);
    return drain(b);
}

int odin_hid_release(struct odin_hid_bridge *b) {
    /* Explicit shutdown cancels any not-yet-delivered new contacts. */
    odin_st_release_all(&b->core);
    discard_and_release(b);
    b->batch_result = ODIN_HID_OK;
    return drain(b);
}
