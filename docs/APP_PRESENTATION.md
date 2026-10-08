# P.T. app presentation

Build 5 displays **P.T.** on the iPad Home Screen and includes an original opaque 1024-pixel P.T. monogram icon. Apple `actool` compiles the asset catalog for iPad, and its generated icon metadata is merged into the application plist. The bundle identifier remains `com.konradkern.pt.native`, preserving the existing application container and saves.

The icon contains no extracted game art or bundled font. Regenerate its source PNG with `python3 tools/make_app_icon.py`, then export any source changes into the patch series. The artwork and generator are covered by this repository's MIT license.

Normal iPad launches skip the initial options screen and retain the original intro. Pause/settings remain available. Explicit `--options-menu` retains the initial options screen for the pinned automated walkthrough, which waits for and dismisses that screen before navigating. Desktop startup behavior is unchanged.

Gameplay touch controls now have a floating movement ring and thumb that track the actual owned finger, a larger **USE** button, a lower **ZOOM** button and a compact pause symbol. The redundant gameplay Back button is removed; Back remains available within menus. The right side supports swiping to look while movement and interaction are held concurrently. Circular button hit areas use the same coordinates and radii as rendering, measured relative to screen height to retain their shape across landscape aspect ratios.

Build 6 additionally shows **SWIPE TO LOOK** only while gameplay look is available, ending the hint after the first look swipe or eight seconds of active gameplay. Intro sequences, pause menus and background time do not consume that allowance. The hint stays dismissed for the remainder of that application session. Patch `0016-transient-look-hint.patch` contains this refinement.

Patch `0015-app-presentation.patch` contains all generated-source changes, including the icon. Fresh reconstruction must match the edited source exactly. Local verification covers the icon catalog/plist, native builds, concurrent touch ownership and thumb bounds, non-overlapping controls across 4:3/16:9/21:9, and original-assets menu/startup integration. A device update and human touch assessment are separate from these local checks; previous physical build 3 measurements do not qualify this layout.
