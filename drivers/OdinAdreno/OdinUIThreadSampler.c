/* SPDX-License-Identifier: BSD-2-Clause
 * Optional, bounded observer compiled against this native XNU's own types.
 * No thread suspension, process signals, user-memory reads or stack walking.
 */
#include <sys/proc_internal.h>
#include <sys/user.h>
#include <kern/thread.h>
#include <kern/clock.h>
#include <pexpert/pexpert.h>
#include <libkern/libkern.h>

#define UI_BANK_WORDS 1024
#define UI_ROW_WORDS 9
#define UI_MAX_ROWS 96
/* sequence, bank, then two banks: version, sequence, ticks, count, proc mask,
 * reserved[3], then tag/pid, tid, state, wait, continuation, user pc/lr/sp, x0.
 * These are approximate per-thread samples, not a globally stopped machine.
 */
volatile uint64_t odin_ui_threads[2 + 2 * UI_BANK_WORDS];
static unsigned started;
extern kern_return_t thread_terminate(thread_t);
extern void odin_ui_sample_thread(thread_t, uint64_t *);
struct ui_capture { uint64_t *bank; unsigned count, process_mask; };

static int sample_proc(proc_t p, void *context)
{
    struct ui_capture *capture = context;
    unsigned tag = 0, per_process = 0;
    if (!strcmp(p->p_comm, "SpringBoard")) tag = 1;
    else if (!strcmp(p->p_comm, "backboardd")) tag = 2;
    else if (!strcmp(p->p_comm, "Preferences")) tag = 3;
    if (!tag || capture->count >= UI_MAX_ROWS) return PROC_RETURNED;
    capture->process_mask |= 1U << tag;
    /* proc_internal.h explicitly requires p_uthlist under proc_lock here;
     * proc_task(p) is unsafe across an exec transition in proc_iterate(). */
    proc_lock(p);
    struct uthread *uth;
    TAILQ_FOREACH(uth, &p->p_uthlist, uu_list) {
        if (capture->count >= UI_MAX_ROWS || per_process++ >= 32) break;
        thread_t thread = get_machthread(uth);
        if (!thread) continue;
        uint64_t *row = capture->bank + 8 + UI_ROW_WORDS * capture->count++;
        row[0] = ((uint64_t)tag << 32) | (uint32_t)proc_pid(p);
        row[1] = uthread_tid(uth);
        odin_ui_sample_thread(thread, row);
    }
    proc_unlock(p);
    return PROC_RETURNED;
}

static void sample_worker(void *unused, wait_result_t result)
{
    (void)unused; (void)result;
    for (uint64_t sequence = 1; sequence <= 1800; ++sequence) {
        unsigned bank_index = (unsigned)(sequence & 1);
        uint64_t *bank = (uint64_t *)&odin_ui_threads[2 + bank_index * UI_BANK_WORDS];
        bzero(bank, UI_BANK_WORDS * sizeof(uint64_t));
        bank[0] = 1; bank[1] = sequence; bank[2] = mach_absolute_time();
        struct ui_capture capture = {bank, 0, 0};
        proc_iterate(PROC_ALLPROCLIST | PROC_NOWAITTRANS, sample_proc, &capture, NULL, NULL);
        bank[3] = capture.count; bank[4] = capture.process_mask;
        __atomic_store_n(&odin_ui_threads[1], bank_index, __ATOMIC_RELEASE);
        __atomic_store_n(&odin_ui_threads[0], sequence, __ATOMIC_RELEASE);
        delay_for_interval(2, NSEC_PER_SEC);
    }
    thread_terminate(current_thread());
}

void odin_ui_sampler_start(void)
{
    unsigned enabled = 0;
    PE_parse_boot_argn("odin-ui-sample", &enabled, sizeof(enabled));
    if (enabled != 1 || !__sync_bool_compare_and_swap(&started, 0, 1)) return;
    thread_t thread = THREAD_NULL;
    if (kernel_thread_start(sample_worker, NULL, &thread) == KERN_SUCCESS)
        thread_deallocate(thread);
}
