/* SPDX-License-Identifier: BSD-2-Clause
 * Fixed-size observations from the signed SpringBoard fixture helper.
 * The userspace endpoint can publish observations only, not kernel addresses
 * or executable commands. The command is read-only to userspace.
 */
#include <sys/sysctl.h>
#include <sys/errno.h>
#include <libkern/libkern.h>

volatile unsigned odin_ui_policy[16];
unsigned odin_ui_policy_command;
static int policy_handler SYSCTL_HANDLER_ARGS
{
    unsigned record[16];
    memcpy(record, (const void *)odin_ui_policy, sizeof(record));
    int error = SYSCTL_OUT(req, record, sizeof(record));
    if (error || !req->newptr) return error;
    if (req->newlen != sizeof(record)) return EINVAL;
    error = SYSCTL_IN(req, record, sizeof(record));
    if (error) return error;
    if (record[0] != 1) return EINVAL;
    memcpy((void *)odin_ui_policy, record, sizeof(record));
    return 0;
}
SYSCTL_PROC(_kern, OID_AUTO, odin_ui_policy,
    CTLTYPE_OPAQUE | CTLFLAG_RW | CTLFLAG_ANYBODY | CTLFLAG_LOCKED,
    0, 0, policy_handler, "S,odin_ui_policy", "RAM UI fixture policy observations");
SYSCTL_UINT(_kern, OID_AUTO, odin_ui_policy_command,
    CTLFLAG_RD | CTLFLAG_LOCKED, &odin_ui_policy_command, 0,
    "RAM UI fixture: zero observes; one requests original idle reset");

/* Diagnostic observations only. No user address or DMA command is accepted. */
static unsigned odin_gpu_probe[16];
extern void odin_gpu_log_append(const char *);
static int gpu_probe_handler SYSCTL_HANDLER_ARGS
{
    unsigned record[16];
    memcpy(record, odin_gpu_probe, sizeof(record));
    int error = SYSCTL_OUT(req, record, sizeof(record));
    if (error || !req->newptr) return error;
    if (req->newlen != sizeof(record)) return EINVAL;
    error = SYSCTL_IN(req, record, sizeof(record));
    if (error) return error;
    if (record[0] != 1 || record[1] > 12) return EINVAL;
    memcpy(odin_gpu_probe, record, sizeof(record));
    char line[256];
    snprintf(line, sizeof(line), "odin surface probe: phase=%u result=%08x id=%u handle=%u bytes=%u %ux%u fence=%u mismatch=%u first=%u got=%08x want=%08x passed=%u\n",
        record[1], record[2], record[3], record[4], record[5], record[6], record[7],
        record[8], record[9], record[10], record[11], record[12], record[15]);
    odin_gpu_log_append(line);
    return 0;
}
SYSCTL_PROC(_kern, OID_AUTO, odin_gpu_probe,
    CTLTYPE_OPAQUE | CTLFLAG_RW | CTLFLAG_ANYBODY | CTLFLAG_LOCKED,
    0, 0, gpu_probe_handler, "S,odin_gpu_probe", "GPU transport probe observations only");

void odin_ui_exit_note(int pid, const char *name, int status, unsigned ns, uint64_t code)
{
    if (strcmp(name, "SpringBoard") && strcmp(name, "backboardd")) return;
    char line[192];
    snprintf(line, sizeof(line), "odin ui exit: pid=%d name=%.16s status=%x namespace=%u code=%llx\n",
             pid, name, status, ns, (unsigned long long)code);
    odin_gpu_log_append(line);
}
