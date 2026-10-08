# Independent native rebuild

This builds the reconstructed C++ `pt-pc` source port for Apple ARM64. Supply your own supported US CUSA01127 v01.00 package and your own development signing profile. Game data is never part of the source release. Use full Xcode, Python 3, Git, CMake, Ninja, glslc, and macOS MoltenVK/Vulkan headers. See [BUILD.md](BUILD.md) for observed tool versions; four compilation jobs are the default. Allow several GiB of free space.

## Fresh source and dependencies

```sh
git clone --recurse-submodules https://github.com/buberlo/pt-ipad.git
cd pt-ipad
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 tools/prepare_source.py
python3 tools/validate_local.py --python-only
```

Begin with no pre-existing `build/` directory. The source pin, eighteen ordered patches and `dependency-lock.json` identify the recipe. Dependencies and downloaded voice models are verified against the lock; observed host compiler/tool versions are recorded rather than claimed bit-reproducible.

## Independently build the target driver

```sh
git clone https://github.com/KhronosGroup/MoltenVK.git build/MoltenVK
git -C build/MoltenVK checkout fae55a18779ee59da2cc5373a367a0282779c171
python3 tools/build_moltenvk.py --root build/MoltenVK
```

The driver builder uses four Xcode jobs, serial dependency builds and an unchanged source checkout. It writes a private `Package/Release/pt-driver-build.json` with the driver archive hash, external dependency revisions and Xcode version. The expected archive is `Package/Release/MoltenVK/static/MoltenVK.xcframework/ios-arm64/libMoltenVK.a`. No existing driver archive qualifies a fresh rebuild.

## Private asset import

```sh
python3 tools/bootstrap_asset_helper.py --install-sdk
python3 tools/import_pt_assets.py /absolute/private/P.T.pkg \
  --extractor .local/asset-helper/published/PT.PkgExtract \
  --private-root assets-private --report reports-private/import.json
```

Use the actual published extractor path printed by the bootstrap helper if it differs. The importer verifies package identity and the exact extracted archive catalogue; a supported manifest and assets are published into `assets-private/CUSA01127`. Unsupported/encrypted packages fail explicitly. Keep the original package unchanged. Saves remain separate. Details: [ASSET_STATUS.md](ASSET_STATUS.md) and [ASSET_INSTALLATION.md](ASSET_INSTALLATION.md).

## Build and local gate

```sh
python3 tools/build_native.py macos --tests --bundle-id org.example.pt --build-number 9
python3 tools/validate_local.py --assets assets-private/CUSA01127
python3 tools/build_native.py ios --bundle-id org.example.pt --build-number 9 \
  --moltenvk-root build/MoltenVK
```

Model downloads stay in ignored build directories. Build manifests record model, source, dependency, driver archive, executable and resource hashes plus observed host tools. Use your own bundle ID consistently. The developer's device keeps the existing default `com.konradkern.pt.native` to preserve its app container.

## Sign and install

```sh
python3 tools/sign_ios.py --bundle-id org.example.pt \
  --app build/ios-arm64/pt.app \
  --profile /absolute/private/development.mobileprovision \
  --identity 'Apple Development: your identity' --output artifacts/PT-build9.ipa
```

The profile must authorize that bundle ID and device; its certificate must match the signature. Manifest/plist identity and built bytes must agree. Old schema-1 manifests are accepted only for the historical default ID. Signer publishes a new signed copy and receipt without changing the input.

For your independently owned iPad, explicitly create a record; for a shared iPad, select its existing record instead:

```sh
python3 tools/ipad_command.py --record /absolute/private/ipad.json \
  --device YOUR_DEVICE_ID --create-record
python3 tools/ipad_command.py --record /absolute/private/ipad.json \
  --device YOUR_DEVICE_ID --session-id rebuild-test --minutes 3 -- \
  xcrun devicectl device install app --device YOUR_DEVICE_ID artifacts/PT-build9/pt.app
python3 tools/ipad_command.py --record /absolute/private/ipad.json \
  --device YOUR_DEVICE_ID --session-id rebuild-test --minutes 5 -- \
  xcrun devicectl device copy to --device YOUR_DEVICE_ID \
  --domain-type appDataContainer --domain-identifier org.example.pt \
  --source assets-private/CUSA01127 --destination Documents/CUSA01127.incoming
python3 tools/device_smoke.py --lease-record /absolute/private/ipad.json \
  --session-id rebuild-test --device YOUR_DEVICE_ID --bundle-id org.example.pt \
  --natural-startup --seconds 90 --output reports-private/first-launch
```

Confirm no existing game session is active before installation/import; preserve it if present. The bounded smoke helper launches in the foreground, verifies exact owned process cleanup and preserves the reservation if cleanup cannot be confirmed. A generic command wrapper alone cannot attest device-process cleanup; use the capture helpers for automated launching. Normal gameplay starts from the installed icon with the original intro and without an initial settings menu.

## Acceptance

A passing local gate, signed bundle or bounded launch is partial evidence. Use [ALPHA_ACCEPTANCE.md](ALPHA_ACCEPTANCE.md) and [DEVICE_TESTING.md](DEVICE_TESTING.md) for ending, actual input/microphone, lifecycle, presentation timing and reboot/offline checks. Retain raw reports locally; publish only source and redacted conclusions. The independent empty-dependency rebuild must have its own report before this gate is marked passed.
