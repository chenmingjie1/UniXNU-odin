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
