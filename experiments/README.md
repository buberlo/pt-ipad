# Unqualified lighting experiment

`opaque-light-zero-contribution.patch` is an optional trial on top of the normal 18-patch Build 9 source. It is deliberately excluded from `patches/series` and normal builds.

The trial skips shadow/material lookups for opaque back-facing surfaces whose diffuse and specular contributions are zero, preserving the output draw/alpha path. Build 10 was built, signed, installed and launched. Native tests and both-mode Mac progression passed (98/98 checkpoints). A short 60-FPS device run ended after background suspension at about 120 seconds.

The f010 GPU sample medians were 28.85 ms total / 8.22 ms lighting, compared with Build 9 pilot values 29.21 / 8.42 ms. Different thermal histories and incomplete scene/visual evidence make this insufficient to establish a benefit or unchanged rendering. **The optimization is not retained in the normal build and is not accepted.** Raw trial data and signed artifacts remain private.

To investigate again, reconstruct the normal source and explicitly apply this patch with `git -C build/port-src apply ../../experiments/opaque-light-zero-contribution.patch`, then build/sign a separate candidate and repeat matched scene and visual checks. Never label the trial stable 1080p/60 from these results.
