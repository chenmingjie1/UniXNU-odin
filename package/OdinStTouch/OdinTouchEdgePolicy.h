// SPDX-License-Identifier: GPL-2.0-only
// Track contacts that began at a physical panel edge through their lift event.
#pragma once
#include <stdint.h>

struct odin_touch_edge_policy {
 uint8_t active[256];
 uint8_t edge[256];
};

static inline bool odin_touch_edge_update(struct odin_touch_edge_policy *state,
 unsigned id,bool touching,int32_t x,int32_t y,bool *began) {
 *began=false;
 if(id>=256)return false;
 if(touching&&!state->active[id]) {
  // IOHIDEvent fixed coordinates, independently normalized on each axis.
  const int32_t edgeX=48*65536/1080,edgeY=48*65536/2400;
  state->edge[id]=x>=0&&x<=65536&&y>=0&&y<=65536&&
   (x<edgeX||x>65536-edgeX||y<edgeY||y>65536-edgeY);
  state->active[id]=1;*began=true;
 }
 bool edge=state->edge[id]!=0;
 if(!touching){state->active[id]=0;state->edge[id]=0;}
 return edge;
}
