"""Minimal implementation of Pipecat's public protobuf frame wire format."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFrame:
    audio: bytes
    sample_rate: int
    num_channels: int


@dataclass(frozen=True)
class MessageFrame:
    message: object


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("protobuf varints must be non-negative")
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _length_delimited(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def serialize_audio(frame: AudioFrame) -> bytes:
    """Serialize an AudioRawFrame nested in Pipecat's Frame oneof."""
    audio = _length_delimited(3, frame.audio)
    audio += _varint(4 << 3) + _varint(frame.sample_rate)
    audio += _varint(5 << 3) + _varint(frame.num_channels)
    return _length_delimited(2, audio)


def deserialize_frame(payload: bytes | str) -> AudioFrame | MessageFrame | None:
    """Read the Pipecat frame types needed by the satellite."""
    if isinstance(payload, str):
        return None
    fields = _fields(payload)
    if 2 in fields:
        audio_fields = _fields(fields[2])
        audio = audio_fields.get(3)
        sample_rate = audio_fields.get(4)
        num_channels = audio_fields.get(5)
        if not isinstance(audio, bytes) or not isinstance(sample_rate, int):
            return None
        if not isinstance(num_channels, int):
            return None
        return AudioFrame(audio, sample_rate, num_channels)
    if 4 in fields and isinstance(fields[4], bytes):
        message_fields = _fields(fields[4])
        data = message_fields.get(1)
        if not isinstance(data, bytes):
            return None
        try:
            return MessageFrame(json.loads(data.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return None


def _read_varint(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(payload) and shift < 70:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("invalid protobuf varint")


def _fields(payload: bytes) -> dict[int, bytes | int]:
    fields: dict[int, bytes | int] = {}
    offset = 0
    while offset < len(payload):
        key, offset = _read_varint(payload, offset)
        field_number, wire_type = key >> 3, key & 7
        if field_number == 0:
            raise ValueError("invalid protobuf field number")
        if wire_type == 0:
            fields[field_number], offset = _read_varint(payload, offset)
        elif wire_type == 1:
            if offset + 8 > len(payload):
                raise ValueError("truncated protobuf fixed64")
            offset += 8
        elif wire_type == 2:
            length, offset = _read_varint(payload, offset)
            end = offset + length
            if end > len(payload):
                raise ValueError("truncated protobuf field")
            fields[field_number] = payload[offset:end]
            offset = end
        elif wire_type == 5:
            if offset + 4 > len(payload):
                raise ValueError("truncated protobuf fixed32")
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
    return fields
