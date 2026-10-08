#include "engine/platform/touch_controls.h"
#include <cassert>
#include <cmath>
#include <limits>

int main() {
    using T = pt::TouchControls;
    T t;
    t.SetAspect(2.f);
    t.Down(1, .15f, .7f);
    t.Motion(1, .23f, .5f);
    auto s = t.Poll();
    assert(s.move_x > 0 && s.move_y > 0);
    assert(std::abs(std::hypot(s.move_x, s.move_y) - 1.f) < .0001f);
    t.Down(2, .65f, .4f);
    t.Motion(2, .7f, .45f);
    t.Down(3, .9f, .72f);
    s = t.Poll();
    assert(s.move_y > 0 && s.look_x > .09f && s.look_y > .04f);
    assert(s.interact && s.interact_pressed);
    s = t.Poll();
    assert(s.interact && !s.interact_pressed && s.look_x == 0);
    t.Up(3);
    assert(!t.Poll().interact);
    // A short tap remains one press even if down and up arrive within one frame.
    t.Down(3, .9f, .72f); t.Up(3);
    s = t.Poll();
    assert(!s.interact && s.interact_pressed);
    assert(!t.Poll().interact_pressed);
    // A held zoom finger cannot become an interaction by sliding across the screen.
    t.Down(4, .77f, .85f); t.Motion(4, .9f, .72f);
    s = t.Poll();
    assert(s.zoom && !s.interact);
    // Reset discards all held controls and accumulated movement after a lifecycle change.
    t.Reset(); s = t.Poll();
    assert(!s.zoom && !s.any && s.move_x == 0 && s.look_y == 0);
    t.Down(5, .92f, .1f); s = t.Poll();
    assert(s.pause && !t.Poll().pause);
    t.Up(5);
    t.Down(6, std::numeric_limits<float>::quiet_NaN(), .2f);
    assert(!t.Poll().any);
    t.Down(7, .1f, .5f); t.Down(7, .9f, .72f);
    assert(!t.Poll().interact);
    t.Reset();
    return 0;
}
