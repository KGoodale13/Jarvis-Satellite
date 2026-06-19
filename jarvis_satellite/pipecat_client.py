"""Pipecat Protobuf-over-WebSocket conversation transport."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from websockets.asyncio.client import connect

from .pipecat_protocol import AudioFrame, MessageFrame, deserialize_frame, serialize_audio

_LOGGER = logging.getLogger(__name__)
_SESSION_END_TYPES = {"session-ended", "session_end", "conversation-ended", "conversation_end"}


class PipecatSession:
    """Run one full-duplex conversation against a Pipecat WebSocket transport."""

    def __init__(
        self,
        *,
        server_url: str,
        auth_token: str | None,
        input_sample_rate: int,
        conversation_timeout: float,
    ) -> None:
        self.server_url = server_url
        self.input_sample_rate = input_sample_rate
        self.conversation_timeout = conversation_timeout
        self._headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes],
        play_audio: Callable[[bytes, int, int], Awaitable[None]],
        on_connected: Callable[[], None],
        on_speaking: Callable[[], None],
    ) -> None:
        _LOGGER.info("Connecting to Pipecat at %s", self.server_url)
        async with connect(
            self.server_url,
            additional_headers=self._headers,
            ping_interval=20,
            ping_timeout=20,
            max_size=4 * 1024 * 1024,
        ) as websocket:
            on_connected()
            _LOGGER.info("Pipecat conversation connected")

            async def send_microphone() -> None:
                while True:
                    pcm = await audio_queue.get()
                    if not pcm:
                        raise RuntimeError("Microphone capture stopped")
                    payload = serialize_audio(
                        AudioFrame(pcm, self.input_sample_rate, 1)
                    )
                    await websocket.send(payload)

            async def receive_server() -> None:
                async for payload in websocket:
                    frame = deserialize_frame(payload)
                    if isinstance(frame, AudioFrame):
                        on_speaking()
                        await play_audio(frame.audio, frame.sample_rate, frame.num_channels)
                    elif isinstance(frame, MessageFrame) and self._is_session_end(
                        frame.message
                    ):
                        _LOGGER.info("Pipecat ended the conversation")
                        return

            async with asyncio.TaskGroup() as tasks:
                sender = tasks.create_task(send_microphone())
                receiver = tasks.create_task(receive_server())
                receiver.add_done_callback(lambda _: sender.cancel())

    def _is_session_end(self, message: object) -> bool:
        if not isinstance(message, dict):
            return False
        message_type = str(message.get("type", "")).lower()
        return message_type in _SESSION_END_TYPES

    async def run_with_timeout(self, *args, **kwargs) -> None:
        if self.conversation_timeout <= 0:
            await self.run(*args, **kwargs)
            return
        async with asyncio.timeout(self.conversation_timeout):
            await self.run(*args, **kwargs)
