// SPDX-License-Identifier: BSD-2-Clause-Patent
#include <AsmMacroLib.h>

ASM_FUNC(DarwinCurrentEl)
  mrs x0, CurrentEL
  ret

// Physical framebuffer markers, no firmware calls after ExitBootServices.
// Each 64-pixel square represents one completed step, left to right:
// green=entry, yellow=cache maintenance, cyan=MMU off, white=kernel branch.
.macro odin_marker index, lo, hi
  cbz x12, 90f
  mov w9, #\lo
  movk w9, #\hi, lsl #16
  mov x10, #64
  add x11, x12, #(\index * 256)
91:
  mov x13, #32
  mov x14, x11
92:
  stp w9, w9, [x14], #8
  subs x13, x13, #1
  b.ne 92b
  add x11, x11, x15
  subs x10, x10, #1
  b.ne 91b
  dsb sy
90:
.endm

// x0=args PA, x1=kernel entry PA, x2=owned PA, x3=owned bytes,
// x4=framebuffer PA, x5=framebuffer bytes, x6=row bytes. EL1 only.
ASM_FUNC(DarwinEnter)
  msr daifset, #15
  mov x12, x4
  mov x15, x6
  // Caller validates at least 256 pixels x 64 rows with a 32-bit framebuffer.
  odin_marker 0, 0xff00, 0xff00
  add x5, x2, x3
  mrs x6, ctr_el0
  ubfx x6, x6, #16, #4
  mov x7, #4
  lsl x6, x7, x6
  sub x7, x6, #1
  bic x4, x2, x7
  dsb sy
1:
  dc civac, x4
  add x4, x4, x6
  cmp x4, x5
  b.lo 1b
  dsb sy
  ic iallu
  dsb sy
  isb
  odin_marker 1, 0xff00, 0xffff
  mrs x4, sctlr_el1
  bic x4, x4, #1
  bic x4, x4, #4
  bic x4, x4, #0x1000
  msr sctlr_el1, x4
  isb
  tlbi vmalle1
  dsb sy
  isb
  odin_marker 2, 0xffff, 0xff00
  odin_marker 3, 0xffff, 0xffff
  br x1
