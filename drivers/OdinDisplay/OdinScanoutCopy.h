// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
// Destination is mapped scanout memory: use aligned scalar/pair stores only.
// No cache-zero instructions, speculative overread, or unaligned libc memcpy.
// Barriers, frame lifetime and mapped range validation remain the caller's.
static inline unsigned odin_copy_scanout_row(volatile uint32_t *destination,
                                            const uint32_t *source,unsigned pixels) {
#if defined(__aarch64__)
 if(!(((uintptr_t)destination|(uintptr_t)source)&7)) {
  while(pixels>=4) {
   uint64_t a,b;
   __asm__ volatile("ldp %0,%1,[%2]\n\tstp %0,%1,[%3]"
       : "=&r"(a),"=&r"(b):"r"(source),"r"(destination):"memory");
   destination+=4;source+=4;pixels-=4;
  }
  if(pixels>=2){*(volatile uint64_t *)destination=*(const uint64_t *)source;
   destination+=2;source+=2;pixels-=2;}
  if(pixels)*destination=*source;
  return 1;
 }
#endif
 for(unsigned x=0;x<pixels;x++)destination[x]=source[x];
 return 0;
}

// Compare cached RAM only; never read the device-mapped scanout for equality.
// Exact comparison avoids hash collisions hiding a visible pixel change.
static inline unsigned odin_scanout_words_equal(const uint32_t *a,const uint32_t *b,unsigned pixels) {
 if(!(((uintptr_t)a|(uintptr_t)b)&7)) {
  while(pixels>=2) {
   if(*(const uint64_t *)a!=*(const uint64_t *)b)return 0;
   a+=2;b+=2;pixels-=2;
  }
 }
 while(pixels--){if(*a++!=*b++)return 0;}
 return 1;
}
// 32-pixel spans preserve unchanged backgrounds without a full device write.
// The caller owns the cached shadow and invalidates it when scanout changes.
static inline unsigned odin_copy_scanout_cached_row(volatile uint32_t *destination,
        const uint32_t *source,uint32_t *shadow,unsigned pixels,unsigned valid) {
 unsigned written=0;
 for(unsigned x=0;x<pixels;) {
  unsigned n=pixels-x;if(n>32)n=32;
  if(!valid||!odin_scanout_words_equal(source+x,shadow+x,n)) {
   odin_copy_scanout_row(destination+x,source+x,n);
   odin_copy_scanout_row(shadow+x,source+x,n);
   written+=n;
  }
  x+=n;
 }
 return written;
}
