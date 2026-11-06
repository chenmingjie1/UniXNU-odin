/* SPDX-License-Identifier: GPL-2.0-only
 * Execute the retained ST wire parser and new HID adapter together.
 */
#include "OdinStHidBridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks, scenarios;
#define CHECK(x) do { checks++; if (!(x)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
struct fixture {
    struct odin_hid_bridge bridge;
    uint8_t events[32][8], reports[128][62], last_attempt[62];
    unsigned events_count, reads, read_cursor, reports_count, attempts, fail_read, fail_send;
};

static bool spi(void *context, const uint8_t *tx, unsigned nt, uint8_t *rx, unsigned nr) {
    struct fixture *f = context;
    if (nt == 5 && tx[0] == 0xfb) {
        CHECK(tx[1] == 0x20 && tx[2] == 0 && tx[3] == 0 && tx[4] == 0 && nr == 3);
        rx[0] = 0xee; rx[1] = 0x36; rx[2] = 0x40; return true;
    }
    if (nt == 3) { CHECK(tx[0] == 0xa0 && tx[1] == 0 && tx[2] == 1 && nr == 0); return true; }
    CHECK(nt == 1 && tx[0] == 0x87 && nr >= 9 && (nr - 1) % 8 == 0);
    f->reads++;
    if (f->fail_read == f->reads) return false;
    const unsigned n = (nr - 1) / 8;
    rx[0] = 0xee;
    memset(rx + 1, 0, nr - 1);
    if (f->events_count) {
        CHECK(f->read_cursor + n <= f->events_count);
        memcpy(rx + 1, f->events + f->read_cursor, n * 8);
        if (f->read_cursor == 0) rx[8] = (uint8_t)(f->events_count - 1);
        f->read_cursor += n;
    }
    return true;
}
static bool hid(void *context, const uint8_t *report, unsigned size) {
    struct fixture *f = context;
    CHECK(size == 62 && report[0] == 3 && report[61] <= 10);
    memcpy(f->last_attempt, report, 62);
    f->attempts++;
    if (f->attempts == f->fail_send) return false;
    CHECK(f->reports_count < 128);
    memcpy(f->reports[f->reports_count++], report, 62);
    return true;
}
static void init(struct fixture *f) {
    memset(f, 0, sizeof *f);
    odin_hid_init(&f->bridge, (struct odin_hid_io){f, spi, f, hid});
    uint8_t id[2]; CHECK(odin_hid_identify(&f->bridge, id));
    CHECK(id[0] == 0x36 && id[1] == 0x40);
    CHECK(odin_hid_start_scan(&f->bridge)); scenarios++;
}
static void batch(struct fixture *f) {
    f->events_count = f->read_cursor = 0;
    memset(f->events, 0, sizeof f->events);
}
static void add(struct fixture *f, unsigned action, unsigned id, unsigned x, unsigned y) {
    CHECK(f->events_count < 32);
    uint8_t *e = f->events[f->events_count++];
    e[0] = (uint8_t)((action << 4) | 3); e[1] = (uint8_t)((id << 4) | 1);
    e[2] = (uint8_t)x; e[3] = (uint8_t)(x >> 8);
    e[4] = (uint8_t)y; e[5] = (uint8_t)(y >> 8);
}
static const uint8_t *contact(struct fixture *f, unsigned report, unsigned id) {
    CHECK(report < f->reports_count);
    for (unsigned i = 0; i < f->reports[report][61]; i++) {
        const uint8_t *p = f->reports[report] + 1 + i * 6;
        if (p[1] == id) return p;
    }
    CHECK(false); return NULL;
}
static unsigned le16(const uint8_t *p) { return p[0] | ((unsigned)p[1] << 8); }

int main(void) {
    struct fixture f;
    /* Whole-batch multislot publication; little-endian axes and saturation. */
    init(&f); add(&f, 1, 5, 0, 0); add(&f, 1, 2, 10800, 24000);
    CHECK(odin_hid_poll(&f.bridge) == 0); CHECK(f.reports_count == 1 && f.reports[0][61] == 2);
    CHECK(le16(contact(&f, 0, 5) + 2) == 0 && le16(contact(&f, 0, 5) + 4) == 0);
    CHECK(le16(contact(&f, 0, 2) + 2) == 32767 && le16(contact(&f, 0, 2) + 4) == 32767);
    batch(&f); add(&f, 3, 2, 65535, 65535); add(&f, 2, 5, 5400, 12000);
    CHECK(odin_hid_poll(&f.bridge) == 0); CHECK(f.reports[1][61] == 2);
    CHECK(contact(&f, 1, 2)[0] == 2 && le16(contact(&f, 1, 2) + 2) == 32767);
    CHECK(contact(&f, 1, 5)[0] == 3 && le16(contact(&f, 1, 5) + 2) > 16000);

    /* A complete tap inside one FIFO must produce a down and an explicit up. */
    init(&f); add(&f, 1, 4, 400, 500); add(&f, 2, 4, 450, 550); add(&f, 3, 4, 0, 0);
    CHECK(odin_hid_poll(&f.bridge) == 0); CHECK(f.reports_count == 2);
    CHECK(contact(&f, 0, 4)[0] == 3 && contact(&f, 1, 4)[0] == 2);
    CHECK(!memcmp(contact(&f, 0, 4) + 2, contact(&f, 1, 4) + 2, 4));
    batch(&f); CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports_count == 2);

    /* A release and repress of the same ID also cannot collapse. */
    init(&f); add(&f, 1, 1, 500, 800); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 3, 1, 0, 0); add(&f, 1, 1, 700, 1000);
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports_count == 3);
    CHECK(contact(&f, 1, 1)[0] == 2 && contact(&f, 2, 1)[0] == 3);

    /* A move followed by lift in one batch must end at the moved position. */
    init(&f); add(&f, 1, 7, 0, 0); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 2, 7, 10799, 23999); add(&f, 3, 7, 0, 0);
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports_count == 3);
    CHECK(contact(&f, 1, 7)[0] == 3 && contact(&f, 2, 7)[0] == 2);
    CHECK(le16(contact(&f, 2, 7) + 2) == 32767 && le16(contact(&f, 2, 7) + 4) == 32767);

    /* Maximum 32 lifecycle events and a full ten-finger drain. */
    init(&f); for (unsigned i = 0; i < 16; i++) { add(&f, 1, 0, i, i); add(&f, 3, 0, 0, 0); }
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports_count == 32 && f.reads == 2);
    init(&f); for (unsigned i = 0; i < 10; i++) add(&f, 1, i, 100 * i, 200 * i);
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports[0][61] == 10);
    batch(&f); for (unsigned i = 0; i < 10; i++) add(&f, 3, 9 - i, 0, 0);
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports[1][61] == 10);
    for (unsigned i = 0; i < 10; i++) CHECK(contact(&f, 1, i)[0] == 2);

    /* Failed HID reports retain the acknowledged state and exact retry bytes. */
    init(&f); f.fail_send = 2; add(&f, 1, 0, 100, 200); add(&f, 3, 0, 0, 0);
    CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SEND_ERROR && f.reports_count == 1);
    uint8_t failed[62]; memcpy(failed, f.last_attempt, 62); unsigned reads = f.reads;
    CHECK(f.bridge.acknowledged.active == 1);
    CHECK(odin_hid_poll(&f.bridge) == 0 && f.reports_count == 2 && f.reads == reads);
    CHECK(!memcmp(failed, f.reports[1], 62) && f.bridge.acknowledged.active == 0);

    /* Corrupt or incomplete batches discard transient contacts; release prior. */
    init(&f); add(&f, 1, 2, 50, 60); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 1, 3, 50, 60); add(&f, 2, 3, 10801, 500);
    CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SENSOR_ERROR && f.reports_count == 2);
    CHECK(f.reports[1][61] == 1 && contact(&f, 1, 2)[0] == 2 && f.bridge.core.active == 0);
    init(&f); add(&f, 1, 2, 50, 60); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 2, 2, 51, 61); add(&f, 1, 3, 50, 60); f.fail_read = f.reads + 2;
    CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SENSOR_ERROR && f.reports_count == 2);
    CHECK(f.reports[1][61] == 1 && contact(&f, 1, 2)[0] == 2);

    /* READY stops this batch, releases all, and blocks further FIFO consumption. */
    init(&f); add(&f, 1, 0, 1, 1); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 0, 0, 0, 0); add(&f, 1, 1, 2, 2);
    CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SCAN_RESTART && f.reports_count == 2);
    CHECK(contact(&f, 1, 0)[0] == 2 && f.bridge.core.active == 0);
    reads = f.reads; CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SCAN_RESTART && f.reads == reads);
    CHECK(odin_hid_start_scan(&f.bridge));

    /* IC error refuses re-identification until explicit driver reinitialization. */
    init(&f); add(&f, 1, 0, 1, 1); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 15, 0, 0, 0); CHECK(odin_hid_poll(&f.bridge) == ODIN_HID_SENSOR_ERROR);
    uint8_t id[2]; CHECK(!odin_hid_identify(&f.bridge, id));

    /* Palm transitions and explicit shutdown cannot leave a held finger. */
    init(&f); add(&f, 1, 3, 10, 20); CHECK(odin_hid_poll(&f.bridge) == 0);
    batch(&f); add(&f, 2, 3, 10, 20); f.events[0][1] = (3 << 4) | 3;
    CHECK(odin_hid_poll(&f.bridge) == 0 && contact(&f, 1, 3)[0] == 2);
    batch(&f); add(&f, 1, 5, 10, 20); CHECK(odin_hid_poll(&f.bridge) == 0);
    f.fail_send = f.attempts + 1;
    CHECK(odin_hid_release(&f.bridge) == ODIN_HID_SEND_ERROR);
    reads = f.reads; CHECK(odin_hid_poll(&f.bridge) == 0 && f.reads == reads);
    CHECK(contact(&f, f.reports_count - 1, 5)[0] == 2);

    /* Exhaustive axis domain: monotonic, endpoints, <=1 HID unit of direct raw. */
    for (unsigned which = 0; which < 2; which++) {
        const unsigned maximum = which ? ODIN_ST_Y_MAX : ODIN_ST_X_MAX;
        unsigned previous = 0;
        for (unsigned raw = 0; raw <= maximum; raw++) {
            unsigned normalized = odin_st_normalize(raw, maximum);
            unsigned converted = (normalized * 32767u + 32767u) / 65535u;
            unsigned direct = (raw * 32767u + maximum / 2u) / maximum;
            CHECK(converted >= previous && converted <= 32767);
            CHECK(abs((int)converted - (int)direct) <= 1);
            previous = converted;
        }
        CHECK(previous == 32767);
    }
    printf("{\"scenarios\":%u,\"assertions\":%u,\"result\":\"passed\"}\n", scenarios, checks);
    return 0;
}
