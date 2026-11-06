/* SPDX-License-Identifier: BSD-2-Clause
 * Compile with the native Mach thread.c recipe, never a BSD/IOKit layout.
 */
#include <kern/thread.h>
#include <kern/spl.h>
#include <mach/arm/thread_status.h>

void odin_ui_sample_thread(thread_t thread, uint64_t *row)
{
    spl_t level = splsched();
    thread_lock(thread);
    row[2] = thread->state;
    row[3] = thread->wait_event;
    row[4] = (uintptr_t)thread->continuation;
    arm_saved_state_t *state = thread->machine.upcb;
    if (state && is_saved_state64(state)) {
        row[5] = get_saved_state_pc(state);
        row[6] = get_saved_state_lr(state);
        row[7] = get_saved_state_sp(state);
        row[8] = get_saved_state_reg(state, 0);
    }
    thread_unlock(thread);
    splx(level);
}
