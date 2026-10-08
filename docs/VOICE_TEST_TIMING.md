# Real-time injected voice timing

The private physical build-3 run `ipad-walkthrough-build3-run3` uses a synthetic local PCM recording through `PT_VOICE_INPUT`. It does not exercise the physical microphone.

The live log through 750 seconds shows f160 enabling recognition at 696.073 seconds, Apple ARM64 Whisper loading its model in 123 ms, and repeated utterance decodes taking 483–498 ms. Actual `VK_GOOGLE_display_timing` rolling rates subsequently fall below 30 FPS (for example 26.936–28.386 near 747–749 seconds). Decode completions coincide with several delayed ten-second status lines. GPU averages alone do not establish the cause of a frame stall.

Source inspection identifies a specific test-path wait: `VoiceRecognizer::Init` already launches a worker, and the Apple worker uses utility QoS. `Feed` queues samples and polls completed detections. In contrast, `Drain` waits until the worker has consumed all pending input and finished processing. The original main loop called `Drain` every frame whenever file input was selected. That blocks the presenting thread during an injected utterance decode. The normal microphone path does not call `Drain`.

Patch `0014-realtime-voice-input.patch` restricts that wait to file input without a window. Headless scripted tests can advance faster than wall time and retain deterministic completion. Windowed file playback now queues audio and consumes completed detections on subsequent frames, using the same asynchronous path as normal microphone input. No inference, keyword matching, or microphone behavior is removed.

This explains an artificial synchronization point in the build-3 verification harness. It does not prove a post-fix presentation rate: the next physical run must correlate the raw actual-presentation CSV with utterance logs and the thermal/power samples added by patch 0013. Preserve build-3 timing and its injection conditions as historical evidence; do not relabel it as steady 30 FPS or physical-microphone validation. Worker CPU contention and any remaining frame stalls must still be measured.
