# Jarvis Satellite

A local-wake-word, full-duplex audio satellite for a Pipecat voice agent. It runs on
Raspberry Pi OS 64-bit and retains the existing hardware integration:

- ReSpeaker XVF3800 USB four-microphone array and its LED ring
- IQaudIO DigiAMP+ HAT for speaker output
- local `hey_jarvis` microWakeWord detection
- PipeWire/PulseAudio device selection, volume, and XVF microphone gain setup

No audio is sent to the server while the satellite is idle. After the wake word,
the satellite opens a WebSocket conversation and streams 16 kHz, mono, signed
16-bit PCM in Pipecat protobuf frames. It concurrently plays the server's 24 kHz,
mono PCM frames, allowing the Pipecat pipeline to support interruption/barge-in.

## Pipecat server contract

The WebSocket endpoint must use Pipecat's `ProtobufFrameSerializer` with a
`FastAPIWebsocketTransport` (or `WebsocketServerTransport`) configured for 16 kHz
input and 24 kHz output:

```python
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_in_sample_rate=16000,
        audio_out_enabled=True,
        audio_out_sample_rate=24000,
        add_wav_header=False,
        serializer=ProtobufFrameSerializer(),
    ),
)
```

The server owns conversation lifetime. Close the WebSocket when the conversation
is over, or send an `OutputTransportMessageFrame` whose `type` is
`session-ended`. The satellite then returns to local wake-word detection. A
configurable maximum duration prevents abandoned sessions from streaming forever.

## Install

On a fresh Raspberry Pi OS Lite 64-bit installation:

```bash
wget -qO- https://raw.githubusercontent.com/KGoodale13/Jarvis-Satellite/refs/heads/main/install_hook.sh | bash
```

Edit `/etc/default/jarvis-satellite` and set the actual endpoint before using the
service:

```bash
PIPECAT_SERVER_URL="ws://192.168.1.100:7860/ws"
# PIPECAT_AUTH_TOKEN="optional-bearer-token"
```

Then restart and inspect the service:

```bash
sudo systemctl restart jarvis-satellite
sudo journalctl -u jarvis-satellite -f
```

Relevant settings in `/etc/default/jarvis-satellite` include explicit audio device
names, input/output volume, XVF microphone gain, output sample rate, conversation
timeout, LED disablement, and debug logging.
