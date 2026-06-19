import json

import pytest

from jarvis_satellite.pipecat_protocol import (
    AudioFrame,
    MessageFrame,
    deserialize_frame,
    serialize_audio,
)


def test_audio_round_trip() -> None:
    frame = AudioFrame(b"\x01\x02\x03\x04", 16000, 1)

    assert deserialize_frame(serialize_audio(frame)) == frame


def test_deserializes_pipecat_audio_with_metadata() -> None:
    # Frame.audio { id: 8, name: "OutputAudioRawFrame#8", audio: ..., rate/channels }
    payload = bytes.fromhex("1222080112154f7574707574417564696f5261774672616d6523301a02010220807d2801")

    assert deserialize_frame(payload) == AudioFrame(b"\x01\x02", 16000, 1)


def test_deserializes_transport_message() -> None:
    data = json.dumps({"type": "session-ended"}).encode()
    nested = b"\x0a" + bytes([len(data)]) + data
    payload = b"\x22" + bytes([len(nested)]) + nested

    assert deserialize_frame(payload) == MessageFrame({"type": "session-ended"})


def test_rejects_truncated_frame() -> None:
    with pytest.raises(ValueError, match="truncated"):
        deserialize_frame(b"\x12\x08\x1a")
