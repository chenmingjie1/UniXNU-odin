// SPDX-License-Identifier: GPL-2.0-only
#include "OdinTouchEdgePolicy.h"
#include <assert.h>
#include <stdio.h>

int main() {
 odin_touch_edge_policy state={};bool began=false;
 // Bottom-starting contact retains its edge metadata as it moves inward/up.
 assert(odin_touch_edge_update(&state,7,true,32768,65500,&began)&&began);
 assert(odin_touch_edge_update(&state,7,true,32768,30000,&began)&&!began);
 assert(odin_touch_edge_update(&state,7,false,32768,30000,&began)&&!began);
 assert(!odin_touch_edge_update(&state,7,false,32768,30000,&began));
 // Reused ID beginning in the center must not inherit an old edge flag.
 assert(!odin_touch_edge_update(&state,7,true,32768,32768,&began)&&began);
 assert(!odin_touch_edge_update(&state,7,true,32768,65500,&began)&&!began);
 assert(!odin_touch_edge_update(&state,7,false,32768,65500,&began));
 // Simultaneous contacts are independent; only the first sample decides.
 assert(odin_touch_edge_update(&state,0,true,0,32000,&began));
 assert(!odin_touch_edge_update(&state,255,true,32000,32000,&began));
 assert(odin_touch_edge_update(&state,0,false,32000,32000,&began));
 assert(!odin_touch_edge_update(&state,255,false,0,32000,&began));
 assert(odin_touch_edge_update(&state,1,true,65536,32000,&began));
 assert(odin_touch_edge_update(&state,2,true,32000,0,&began));
 assert(!odin_touch_edge_update(&state,256,true,0,0,&began)&&!began);
 assert(!odin_touch_edge_update(&state,3,true,-1,32000,&began));
 assert(!odin_touch_edge_update(&state,4,true,32000,65537,&began));
 puts("Edge contact lifetime, release, ID reuse and multitouch scenarios passed");
}
