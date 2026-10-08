# Contributing

P.T. for iPad compiles the reconstructed C++ runtime from the pinned `pt-pc` revision for ARM64. Original game assets are supplied privately by each user.

Use small `codex/…` branches. Keep `upstream/pt-pc` clean at the commit in `source-lock.json`. Prepare source with `tools/prepare_source.py`, edit the ignored generated `build/port-src`, and export only the incremental changes as the next ordered patch under `patches/`. Add it to `patches/series`; retain exact source licenses and provenance. Never commit a generated source checkout in place of a patch.

Before submitting, reconstruct into a fresh output directory and compare its source hash with your edited source. Run `python3 tools/validate_local.py` after `python3 tools/build_native.py macos --tests`. Asset-dependent tests require an explicit `--assets` directory. `--python-only` is a partial tooling gate and cannot substitute for native tests. Record commands, tool versions, source/build identity and results in the change description. Changes affecting renderer/gameplay need matching original-assets and device evidence.

Do not commit packages, extracted assets, models, profiles, credentials, signed apps, recordings or private reports. GitHub Actions must remain disabled; validation is local. Physical-device commands must use the repository lease coordinator, the existing shared record where applicable, a bounded duration and exact process cleanup. Preserve other sessions and queued work.

Build, signature, installation, foreground launch, gameplay and acceptance are separate evidence states. Report what was exercised, what failed and what remains unverified.
