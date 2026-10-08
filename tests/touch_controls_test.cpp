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
    auto visual = t.MovementVisual();
    assert(visual.active && visual.x == .15f && visual.y == .7f);
    assert(std::abs(std::hypot((visual.thumb_x - visual.x) * 2.f, visual.thumb_y - visual.y) - T::move_radius) < .0001f);
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
    t.Down(4, .81f, .87f); t.Motion(4, .9f, .72f);
    s = t.Poll();
    assert(s.zoom && !s.interact);
    // Reset discards all held controls and accumulated movement after a lifecycle change.
    t.Reset(); s = t.Poll();
    assert(!s.zoom && !s.any && s.move_x == 0 && s.look_y == 0);
    assert(!t.MovementVisual().active);
    t.Down(5, .92f, .1f); s = t.Poll();
    assert(s.pause && !t.Poll().pause);
    t.Up(5);
    t.Down(6, std::numeric_limits<float>::quiet_NaN(), .2f);
    assert(!t.Poll().any);
    t.Down(7, .1f, .5f); t.Down(7, .9f, .72f);
    assert(!t.Poll().interact);
    t.Reset();
    // Visible gameplay buttons remain distinct circles across supported landscape displays.
    for (float aspect : {4.f/3, 16.f/9, 21.f/9}) {
        for (size_t i = 0; i < T::buttons.size(); ++i) {
            const auto& a = T::buttons[i];
            assert(a.x * aspect > a.radius && (1 - a.x) * aspect > a.radius);
            assert(a.y > a.radius && 1 - a.y > a.radius);
            for (size_t j = i + 1; j < T::buttons.size(); ++j) {
                const auto& b = T::buttons[j];
                assert(std::hypot((a.x-b.x)*aspect, a.y-b.y) > a.radius+b.radius);
            }
        }
    }
    return 0;
}
