# Jarvis Satellite

A local-wake-word, full-duplex SmallWebRTC satellite for a Pipecat voice agent.
It runs on Raspberry Pi OS 64-bit and retains the existing hardware integration:

- ReSpeaker XVF3800 USB four-microphone array and LED ring
- IQaudIO DigiAMP+ HAT for speaker output
- local `hey_jarvis` microWakeWord detection
- PipeWire/PulseAudio device selection, volume, and XVF microphone gain setup
- hardware AEC reference routing from DigiAMP+ playback to the XVF3800

No audio leaves the satellite while it is idle. After the wake word, it creates a
SmallWebRTC session with Pipecat and sends a mono microphone track. Returned Opus
audio is decoded, resampled to 24 kHz mono PCM, and played through the DigiAMP+.
WebRTC provides jitter buffering, congestion control, clock synchronization, and
native interruption handling.

At service startup, PipeWire creates a combined output sink. It mirrors bot audio
to the DigiAMP+ and the ReSpeaker USB playback endpoint. The USB stream supplies
the XVF3800's far-end reference, allowing its onboard AEC to remove speaker audio
from microphone capture. Set `JARVIS_ENABLE_HARDWARE_AEC="0"` only for diagnostics.

## Pipecat server contract

The server must expose Pipecat's SmallWebRTC signaling endpoint. The standard
Pipecat development runner provides this at `/api/offer` when launched with the
`webrtc` transport:

```bash
python -m pipecat_server.bot --transport webrtc --host 0.0.0.0 --port 7860
```

The satellite waits for local ICE gathering and then posts its SDP offer to:

```text
http://pipecat:7860/api/offer
```

## Install

On a fresh Raspberry Pi OS Lite 64-bit installation:

```bash
wget -qO- https://raw.githubusercontent.com/KGoodale13/Jarvis-Satellite/refs/heads/main/install_hook.sh | bash
```

The default server URL is suitable when the Pipecat host resolves as `pipecat`.
Override it in `/etc/default/jarvis-satellite` when necessary:

```bash
PIPECAT_SERVER_URL="http://pipecat:7860/api/offer"
```

Then restart and inspect the service:

```bash
sudo systemctl restart jarvis-satellite
sudo journalctl -u jarvis-satellite -f
```

Relevant settings include explicit audio device names, input/output volume, XVF
microphone gain, conversation timeout, LED disablement, and debug logging.
