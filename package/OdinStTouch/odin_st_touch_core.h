/* SPDX-License-Identifier: GPL-2.0-only
 * ST FTM5/SALIXP protocol for odin, not FocalTech's unrelated "FTS 5.x".
 * References: MiCode/Xiaomi_Kernel_OpenSource odin-r-oss commit
 * f82406097ede3943a96c08b95bd1f5b5149ee0f0, drivers/input/touchscreen/fts_spi/
 * fts.c (enter/leave handlers, FIFO drain), fts_lib/fts{Hardware,Software,IO}.*.
 * Native bus and HID posting are callbacks so wire handling is executable on a host.
 */
#ifndef ODIN_ST_TOUCH_CORE_H
#define ODIN_ST_TOUCH_CORE_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define ODIN_ST_CONTACTS 10u
#define ODIN_ST_EVENT_BYTES 8u
#define ODIN_ST_FIFO_EVENTS 32u
/* DT gives extents; the live Android POSITION axes expose extent - 1. */
#define ODIN_ST_X_EXTENT 10800u
#define ODIN_ST_Y_EXTENT 24000u
#define ODIN_ST_X_MAX (ODIN_ST_X_EXTENT - 1u)
#define ODIN_ST_Y_MAX (ODIN_ST_Y_EXTENT - 1u)
#define ODIN_ST_DOWN 1u
#define ODIN_ST_MOVE 2u
#define ODIN_ST_UP 3u

/* transfer must keep CS asserted between TX and RX, MSB first, SPI mode 0.
 * RX includes the ST dummy byte. tx/rx may be NULL only for a zero byte count.
 * It must return false on an incomplete transfer; it may not retry a FIFO read.
 */
struct odin_st_bus {
    void *context;
    bool (*transfer)(void *, const uint8_t *, unsigned, uint8_t *, unsigned);
    void (*post)(void *, unsigned, unsigned, uint32_t, uint32_t);
};

struct odin_st_state {
    struct odin_st_bus bus;
    uint32_t active;
    uint32_t x[ODIN_ST_CONTACTS], y[ODIN_ST_CONTACTS];
    uint32_t reports, down, move, up, ignored, malformed, failures, resets;
    bool identified, scan_restart_needed, faulted;
};

static inline void odin_st_init(struct odin_st_state *s, struct odin_st_bus bus) {
    *s = (struct odin_st_state){0};
    s->bus = bus;
}

static inline void odin_st_release_all(struct odin_st_state *s) {
    for (unsigned id = 0; id < ODIN_ST_CONTACTS; id++) {
        if (s->active & (1u << id)) {
            s->bus.post(s->bus.context, ODIN_ST_UP, id, s->x[id], s->y[id]);
            s->up++;
        }
    }
    s->active = 0;
}

static inline uint32_t odin_st_normalize(uint32_t value, uint32_t maximum) {
    return (value * 65535u + maximum / 2u) / maximum;
}

/* Eight event bytes, after stripping the SPI dummy. The real odin FDT has
 * support-super-resolution=1: X/Y are LE16, POSITION range 0..10799/0..23999.
 * The vendor handler can emit the extent itself; saturate that one-step edge
 * value, but reject larger values rather than inventing a valid edge touch.
 * On lift use the last position, since vendor leave payload coordinates differ.
 */
static inline bool odin_st_event(struct odin_st_state *s, const uint8_t e[8]) {
    if (e[0] == 0) return true;
    unsigned event = e[0] >> 4;
    if (e[0] == 0x03 || event == 15) {
        /* Ready can restart scanning; a controller error stops this adapter. */
        if ((e[0] & 3u) != 3u) { s->malformed++; return false; }
        odin_st_release_all(s);
        s->resets++;
        if (e[0] == 0x03) {
            s->scan_restart_needed = true;
        } else {
            s->scan_restart_needed = false;
            s->faulted = true;
            s->identified = false;
            return false;
        }
        return true;
    }
    if (event < 1 || event > 3) { s->ignored++; return true; }
    unsigned id = e[1] >> 4, type = e[1] & 15u;
    if ((e[0] & 3u) != 3u || id >= ODIN_ST_CONTACTS) {
        s->malformed++;
        return false;
    }
    if (event == 3 || (type != 1 && type != 2)) {
        /* Leave can have no type. Any non-finger/glove transition is lifted;
         * this includes palm, stylus, hover and invalid so a slot cannot stick.
         */
        if (s->active & (1u << id)) {
            s->bus.post(s->bus.context, ODIN_ST_UP, id, s->x[id], s->y[id]);
            s->up++;
            s->active &= ~(1u << id);
        }
        if (event != 3) s->ignored++;
        return true;
    }
    uint32_t x = (uint32_t)e[2] | ((uint32_t)e[3] << 8);
    uint32_t y = (uint32_t)e[4] | ((uint32_t)e[5] << 8);
    if (x > ODIN_ST_X_EXTENT || y > ODIN_ST_Y_EXTENT) {
        /* Reject a corrupted coordinate instead of turning it into an edge tap. */
        s->malformed++;
        return false;
    }
    if (x > ODIN_ST_X_MAX) x = ODIN_ST_X_MAX;
    if (y > ODIN_ST_Y_MAX) y = ODIN_ST_Y_MAX;
    x = odin_st_normalize(x, ODIN_ST_X_MAX);
    y = odin_st_normalize(y, ODIN_ST_Y_MAX);
    unsigned action = s->active & (1u << id) ? ODIN_ST_MOVE : ODIN_ST_DOWN;
    s->x[id] = x;
    s->y[id] = y;
    s->bus.post(s->bus.context, action, id, x, y);
    s->active |= 1u << id;
    if (action == ODIN_ST_DOWN) s->down++; else s->move++;
    return true;
}

static inline bool odin_st_hw_read(struct odin_st_state *s, uint32_t address,
                                 uint8_t *out, unsigned count) {
    uint8_t command[5] = {0xfb, (uint8_t)(address >> 24), (uint8_t)(address >> 16),
                          (uint8_t)(address >> 8), (uint8_t)address};
    uint8_t receive[9] = {0};
    if (!s->bus.transfer || !out || !count || count > 8) return false;
    if (!s->bus.transfer(s->bus.context, command, 5, receive, count + 1)) return false;
    for (unsigned i = 0; i < count; i++) out[i] = receive[i + 1];
    return true;
}

static inline bool odin_st_identify(struct odin_st_state *s, uint8_t id[2]) {
    s->identified = false;
    if (s->faulted) return false; /* require explicit driver restart after IC error */
    if (!odin_st_hw_read(s, 0x20000000u, id, 2)) return false;
    s->identified = id[0] == 0x36 && id[1] == 0x40;
    return s->identified;
}

/* Only a volatile active-multitouch scan command. No reset/calibration,
 * firmware download, flash, lockdown, or arbitrary register write API exists.
 */
static inline bool odin_st_enable_scan(struct odin_st_state *s) {
    static const uint8_t command[3] = {0xa0, 0, 1};
    return s->identified && s->bus.transfer(s->bus.context, command, 3, NULL, 0);
}

static inline bool odin_st_fifo_read(struct odin_st_state *s, uint8_t *out,
                                    unsigned events) {
    static const uint8_t command = 0x87;
    uint8_t receive[ODIN_ST_FIFO_EVENTS * ODIN_ST_EVENT_BYTES + 1] = {0};
    if (!s->identified || events == 0 || events > ODIN_ST_FIFO_EVENTS) return false;
    unsigned bytes = events * ODIN_ST_EVENT_BYTES;
    if (!s->bus.transfer(s->bus.context, &command, 1, receive, bytes + 1)) return false;
    for (unsigned i = 0; i < bytes; i++) out[i] = receive[i + 1];
    return true;
}

static inline bool odin_st_poll(struct odin_st_state *s) {
    uint8_t events[ODIN_ST_FIFO_EVENTS * ODIN_ST_EVENT_BYTES] = {0};
    if (!odin_st_fifo_read(s, events, 1)) {
        s->failures++;
        odin_st_release_all(s);
        return false;
    }
    if (events[0] == 0) return true;
    unsigned remaining = events[7] & 31u;
    if (remaining && !odin_st_fifo_read(s, events + 8, remaining)) {
        s->failures++;
        odin_st_release_all(s);
        return false;
    }
    s->reports++;
    for (unsigned i = 0; i <= remaining; i++) {
        if (events[i * 8] == 0) break;
        if (!odin_st_event(s, events + i * 8)) {
            odin_st_release_all(s);
            return false;
        }
        /* A READY invalidates later contacts already fetched in this batch.
         * Return to the worker for a full resync before publishing more input. */
        if (s->scan_restart_needed) break;
    }
    return true;
}
#endif
