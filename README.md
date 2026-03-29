# Jarvis-Satellite

Hardware-specific install and runtime glue for running
[OHF Linux Voice Assistant](https://github.com/OHF-Voice/linux-voice-assistant)
on a Raspberry Pi with:

- ReSpeaker XVF3800 USB mic array
- IQaudIO DigiAMP+ HAT
- Raspberry Pi OS 64-bit

This repository no longer provisions `wyoming-satellite`. It now:

- installs a pinned upstream `linux-voice-assistant` checkout
- configures PipeWire/PulseAudio defaults for the ReSpeaker + DigiAMP hardware
- keeps the XVF3800 LED ring integration for wake/listen/mute/disconnect states
- tracks the upstream `respeaker_xvf3800` tooling as a submodule

On a fresh Raspberry Pi OS Lite 64-bit installation:

```bash
wget -qO- https://raw.githubusercontent.com/KGoodale13/Jarvis-Satellite/refs/heads/main/install_hook.sh | bash
```

After install:

1. Add the satellite in Home Assistant with the `ESPHome` integration on port `6053`.
2. Check the service with `sudo systemctl status jarvis-satellite`.
3. Adjust `/etc/default/jarvis-satellite` if you need to override names, network interface, wake model, or explicit audio device names.
