# Native touch menus

Patch `0010-native-touch-menu.patch` fixes the first-boot options screen and pause/settings navigation. The preceding source files were byte-identical to `build/repro-final3` (patches 0001–0009) before editing.

The original game uses keyboard and controller menu actions. The first iPad build supplied gameplay touch actions but disabled mouse emulation and menu pointer input. Consequently, tapping visible rows did nothing; the overlay's Back action did not close the original options screen; Interact opened PC settings; camera inversion required absent keyboard/controller buttons. The top-right Pause control could close first boot, but its labeling did not explain that action.

On iPad, an open menu now shows Continue, Back, Settings (or Select on a settings page), Zoom, and a Navigate joystick. Continue closes either menu page, including first boot. Back returns from a settings submenu or closes the original options screen. Tapping a visible original settings row changes brightness, subtitle language, or camera inversion through the existing game UI hit tests. Settings pages accept row taps and joystick/Select navigation. Zoom remains available for the original photo-option puzzle. Gameplay touch controls are unchanged.

Menu taps are generated on release, survive a down/up pair in one frame, and reject canceled or dragged touches. Switching between gameplay and menus clears owned fingers and accumulated look movement. Output pixels are mapped through the same integer fitted rectangle used by `Renderer::EndFrame` into the fixed 1920×1080 game frame, then through `UiCanvas` into UI units. Black-bar taps cannot activate game menu rows. The native overlay itself stays in display coordinates.

Native menus hide keyboard/controller glyphs and desktop Quit, rename PC Settings to Settings, and show touch instructions. New overlay labels are currently English; the game's existing localized option names remain intact. This is a targeted navigation repair, not a complete redesign of optional desktop extras such as photo mode or free camera.

## Verification

- `tests/touch_controls_test.cpp` exercises unchanged gameplay ownership, simultaneous controls, tap edges, and background resets.
- Generated `tests/ipad_input_test.cpp` feeds SDL finger events into the real `InputDevice`, then maps menu actions. It covers Continue/Back/Select, row taps, cancellation, drag rejection, menu transitions, gameplay look, and output-to-UI mapping at 2732×2048, 2160×1620, 1920×1080, and 2560×1080.
- With no argument, `pt_ipad_input_test` is asset-free and remains a CTest target. Supplying a privately imported game folder additionally loads the original option model/animations and tests first-boot Back/Continue, both inversion rows, settings entry and value change, Back, direct Continue from settings, and preservation of desktop Backspace behavior:

  ```sh
  build/macos-arm64/pt_ipad_input_test assets-private/CUSA01127
  ```

- Host C++ syntax and iOS `main.cpp` syntax checks passed before export. The original standalone touch test passed. The coordinated Mac build of patches 0001–0013 passed: 22 asset-free checks and 31 checks with the original assets (the latter includes the 22 asset-free checks). Private logs are in `reports-private/touch-menu-build4/`. One pre-existing missing `UI_sys_opt_setin_s` animation warning occurs on settings-page return; no test failed. A physical iPad touch walkthrough remains required; event injection does not prove a human touch flow.

## Thermal and power metadata

Patch `0013-ios-thermal-telemetry.patch` adds the OS-reported thermal-pressure state and Low Power Mode at startup and alongside each ten-second status sample. The sample also reports the existing `VK_GOOGLE_display_timing` actual presentation rate and observed presentation count. Unsupported thermal/power information is explicitly unavailable, and unavailable presentation rate stays unavailable. Thermal pressure is not a temperature reading; ten-second samples do not rule out changes between samples. This metadata supports performance qualification but does not itself establish acceptable sustained performance.
