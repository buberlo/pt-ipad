# Physical iPad validation

The local test tools use a shared-device coordinator to prevent concurrent installations and measurements. Every device operation in this workspace must hold the `pt-native` command lease for this chat. Another owner, a paused record, or an unconfirmed earlier cleanup blocks a new operation; expired timestamps do not grant takeover permission. Other queued work remains in the record. This coordination policy is separate from the game's C++ runtime and is not an application dependency.

Configure the record through `PT_IPAD_LEASE_RECORD` or `tools/ipad_command.py --record /absolute/path/ipad-access.json`; select the locally installed compatible coordinator through `--lease-wrapper /absolute/path/with-ipad-lease.py`. Historical default paths refer to the original development workspace. The public repository does not include that external coordinator, so an independent checkout must configure it before using these guarded capture helpers. Normal Xcode installation of the native application is independent of these test helpers; follow the applicable device-access policy before any physical-device action.

## Build, sign and install

Follow [BUILD.md](BUILD.md), then sign with `tools/sign_ios.py`. Keep the returned signed app, IPA, signing receipt and game archives private. Each native build records its source tree and dependency inputs. Confirm the intended build number before installation; source compilation and a valid signature are separate from installation and runtime evidence.

Use an explicit device ID with the lease wrapper for installation and file copying. New assets are copied to `Documents/CUSA01127.incoming`; the application hashes and activates them on its next launch. [ASSET_INSTALLATION.md](ASSET_INSTALLATION.md) describes rejection and rollback. Never copy over a running installation or mix saves into the asset directory.

## Bounded scene check

```sh
python3 tools/device_smoke.py --device "$PT_DEVICE" \
  --output reports-private/device-smoke-new-build --seconds 45
```

This uses the installed app, captures fresh device screenshots and retains its runtime log. It refuses to replace an existing P.T. session and terminates only the process created by its own recorded launch. An early exit is a failed check. It does not establish touchscreen behavior or complete gameplay.

Launch helpers require a cleanup receipt carrying their lease token. The reservation is retained if interruption or communication failure prevents confirming device-process cleanup. Inspect the run's launch response and process identity before recovery; never clear the shared record or terminate an unrelated process merely to make another run start.

## Scripted rendering and timing

```sh
python3 tools/device_walkthrough.py --device "$PT_DEVICE" \
  --output reports-private/device-walkthrough-new-build --seconds 1500 \
  --app artifacts/PT-Native-build4/pt.app
```

The helper uses the pinned full walkthrough at normal demo speed, original assets, seed 1 and a foreground window. Source-generated route files, fresh settings/logs and presentation CSV live in a unique private device session directory. The route includes an injected voice result; this is not live microphone or physical-controller acceptance. Screenshots and milestone/error logs must be reviewed alongside the trace.

The foreground preface reuses upstream `speedrun_boot.txt` to dismiss the real first-boot options menu with a scripted Escape key. It then waits for the menu to close and controller step 15 before the unchanged `FULL` route begins. The source hashes and preface are recorded separately. The helper checks startup logs at 30, 60 and 90 seconds and stops if `StartGame` is absent at 90 seconds; display timing on the options menu cannot qualify as gameplay.

From patch `0012`, route screenshots use the original internal render size (1920×1080 on this iPad configuration), including the original game UI and final grain/brightness. They exclude the display's letterbox bars and native touch overlay. Periodic device screenshots retain the full display. The capture fix passed a real, asset-free Mac GPU regression; its iPad capture path still needs verification in the resulting installed build. Preserve older failed screenshot records.

The opt-in `PT_PRESENT_TRACE_PATH` records actual `VK_GOOGLE_display_timing` timestamps. Parse retained data with:

```sh
python3 tools/summarize_present_trace.py trace.csv \
  --output summary.json --warmup-seconds 30 --window-seconds 60
```

Warmup applies at each segment boundary. Keep loading, pauses, trace gaps and ending-idle time separate from representative gameplay. A long process lifetime or high average rate cannot establish the 20-minute, p95 ≤40 ms target. No helper automatically declares acceptance.

On interruption, the helper prioritizes exact-owned process teardown and skips further artifact copies. Already retained runtime logs and screenshots are partial evidence; a final presentation CSV may be unavailable. The cleanup receipt proves only that the invocation's processes are gone, not that its requested test completed.

## Physical controls and lifecycle

`tests/ios` contains an independent XCTest harness that sends actual touch gestures, captures results, backgrounds and resumes the application. Generate its project under ignored `build/device-tests` using XcodeGen; use a local signing team and run tests only under the lease. The first attempt on this host failed during Xcode's automation-mode initialization: **zero test methods executed**. This is an outstanding test-infrastructure gate, not a passing touchscreen check or evidence of an app input failure.

Rebuild the signed XCTest products from the current Swift source before retrying; the updated test requires `PT_TEST_SESSION`. Select its generated `.xctestrun` file explicitly:

```sh
python3 tools/device_ui_test.py --device "$PT_DEVICE" \
  --app artifacts/PT-build6/pt.app --xctestrun "$PT_XCTESTRUN" \
  --output reports-private/device-ui-new-build --seconds 240
```

This performs one bounded test attempt. Before installation it rejects existing P.T., harness or test-runner processes. Under the lease it installs the selected signed products and records the exact bundle installation paths. Only new processes at paths verified by their bundle identity can become cleanup targets; an uncertain identity retains the reservation for explicit recovery. Xcode stays in the lease supervisor's process group. The tool never changes automation preferences or other apps.

Success requires the exact `PTDeviceTests/NativeInputTests/testTouchAndResume` test to execute and pass, plus fresh application logs from its isolated session. The input script only logs state: postanalysis requires gameplay samples at controller step 15 on f010, a yaw change of at least 0.15 radians, horizontal movement of at least 0.25 metres, and pause-close/background-resume events. Opening-demo motion and app foreground state alone do not pass. These checks support look/move and lifecycle evidence; screenshot review, interact/zoom behavior, held-input reset and wider control acceptance remain separate. A preflight refusal before installation is not another XCTest bootstrap attempt.

Final acceptance also requires controller input/disconnects, live microphone permission and recognition, audio interruptions, saves, complete ending, original-reference visual comparisons, and a reboot/offline launch with development tools disconnected. Keep built, signed, installed, launched, playable and accepted states separate in [STATUS.md](STATUS.md).
