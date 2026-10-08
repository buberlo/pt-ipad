# P.T. iPad working rules

- Implement the approved native C++ source-port plan in docs/PLAN.md. Do not introduce Wine, FEX, an emulator runtime, or CPU JIT.
- Never create, enable, propose or run GitHub Actions. Check remote Actions remain disabled before pushes.
- Keep upstream/pt-pc pinned and clean. Edit generated build/port-src and export ordered patches. A fresh generated checkout must reproduce every source change.
- Never commit game packages, extracted game data, recordings, signed applications, credentials, provisioning profiles or model downloads. Keep original package files unchanged.
- Preserve source licenses and exact provenance. The copied probes are MIT; the Madeira/Penta applications and AnyPS5 core have different licenses.
- Before any physical-device operation, acquire a bounded lease using the shared record configured in PT_IPAD_LEASE_RECORD. Default local record: ../madeira/installation/ipad-access.json. Respect other owners and queued work. Do not restart paused projects.
- Do not claim gameplay from a successful build, install, swapchain or probe. Record actual device identity, source/build identity, assets, foreground state, images and presentation timing when testing.
- Keep build parallelism at four jobs by default. Check storage before extraction and large builds; preserve other projects' data.
