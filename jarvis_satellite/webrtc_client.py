"""SmallWebRTC conversation transport for the Jarvis satellite."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from fractions import Fraction
from urllib.request import Request, urlopen

import av
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError

_LOGGER = logging.getLogger(__name__)


class MicrophoneAudioTrack(MediaStreamTrack):
    """Expose captured PCM16 microphone samples as a paced WebRTC audio track."""

    kind = "audio"

    def __init__(self, audio_queue: asyncio.Queue[bytes], sample_rate: int) -> None:
        super().__init__()
        self._audio_queue = audio_queue
        self._sample_rate = sample_rate
        self._samples_per_frame = sample_rate // 50  # 20 ms
        self._buffer = bytearray()
        self._pts = 0
        self._started_at: float | None = None

    async def recv(self) -> av.AudioFrame:
        frame_bytes = self._samples_per_frame * 2
        while len(self._buffer) < frame_bytes:
            pcm = await self._audio_queue.get()
            if not pcm:
                raise MediaStreamError
            self._buffer.extend(pcm)

        loop = asyncio.get_running_loop()
        if self._started_at is None:
            self._started_at = loop.time()
        else:
            target = self._started_at + (self._pts / self._sample_rate)
            await asyncio.sleep(max(0.0, target - loop.time()))

        pcm = bytes(self._buffer[:frame_bytes])
        del self._buffer[:frame_bytes]
        frame = av.AudioFrame(format="s16", layout="mono", samples=self._samples_per_frame)
        frame.planes[0].update(pcm)
        frame.sample_rate = self._sample_rate
        frame.pts = self._pts
        frame.time_base = Fraction(1, self._sample_rate)
        self._pts += self._samples_per_frame
        return frame


class SmallWebRTCSession:
    """Run one full-duplex conversation using Pipecat SmallWebRTC signaling."""

    def __init__(
        self,
        *,
        server_url: str,
        auth_token: str | None,
        input_sample_rate: int,
        output_sample_rate: int,
        conversation_timeout: float,
    ) -> None:
        self.server_url = server_url
        self.auth_token = auth_token
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.conversation_timeout = conversation_timeout

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes],
        play_audio: Callable[[bytes, int, int], Awaitable[None]],
        on_connected: Callable[[], None],
        on_speaking: Callable[[], None],
    ) -> None:
        peer = RTCPeerConnection()
        microphone = MicrophoneAudioTrack(audio_queue, self.input_sample_rate)
        peer.addTrack(microphone)
        data_channel = peer.createDataChannel("chat", ordered=True)
        disconnected = asyncio.Event()
        playback_tasks: set[asyncio.Task[None]] = set()

        @data_channel.on("open")
        def on_data_channel_open() -> None:
            data_channel.send(
                json.dumps(
                    {
                        "type": "signalling",
                        "message": {
                            "type": "trackStatus",
                            "receiver_index": 0,
                            "enabled": True,
                        },
                    }
                )
            )

        @peer.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            _LOGGER.info("SmallWebRTC connection state: %s", peer.connectionState)
            if peer.connectionState in {"closed", "failed", "disconnected"}:
                disconnected.set()

        @peer.on("track")
        def on_track(track: MediaStreamTrack) -> None:
            if track.kind != "audio":
                return
            task = asyncio.create_task(
                self._play_remote_audio(track, play_audio, on_speaking)
            )
            playback_tasks.add(task)
            task.add_done_callback(playback_tasks.discard)

        try:
            offer = await peer.createOffer()
            await peer.setLocalDescription(offer)
            await self._wait_for_ice_gathering(peer)
            local = peer.localDescription
            if local is None:
                raise RuntimeError("WebRTC did not create a local offer")

            answer = await asyncio.to_thread(self._send_offer, local)
            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
            )
            await self._wait_for_connected(peer, disconnected)
            on_connected()
            _LOGGER.info("SmallWebRTC conversation connected (pc_id=%s)", answer.get("pc_id"))

            if self.conversation_timeout > 0:
                async with asyncio.timeout(self.conversation_timeout):
                    await disconnected.wait()
            else:
                await disconnected.wait()
        finally:
            microphone.stop()
            for task in playback_tasks:
                task.cancel()
            if playback_tasks:
                await asyncio.gather(*playback_tasks, return_exceptions=True)
            await peer.close()

    async def run_with_timeout(self, *args, **kwargs) -> None:
        await self.run(*args, **kwargs)

    def _send_offer(self, offer: RTCSessionDescription) -> dict[str, object]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        request = Request(
            self.server_url,
            data=json.dumps({"sdp": offer.sdp, "type": offer.type}).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            answer = json.load(response)
        if not isinstance(answer, dict) or not isinstance(answer.get("sdp"), str):
            raise RuntimeError("Pipecat returned an invalid WebRTC answer")
        if answer.get("type") != "answer":
            raise RuntimeError(f"Pipecat returned unexpected SDP type: {answer.get('type')}")
        return answer

    async def _play_remote_audio(
        self,
        track: MediaStreamTrack,
        play_audio: Callable[[bytes, int, int], Awaitable[None]],
        on_speaking: Callable[[], None],
    ) -> None:
        resampler = av.AudioResampler(
            format="s16", layout="mono", rate=self.output_sample_rate
        )
        try:
            first_frame = True
            while True:
                incoming = await track.recv()
                if first_frame:
                    on_speaking()
                    first_frame = False
                for frame in resampler.resample(incoming):
                    await play_audio(
                        frame.to_ndarray().tobytes(), self.output_sample_rate, 1
                    )
        except MediaStreamError:
            _LOGGER.info("Pipecat remote audio track ended")

    async def _wait_for_ice_gathering(self, peer: RTCPeerConnection) -> None:
        if peer.iceGatheringState == "complete":
            return
        complete = asyncio.Event()

        @peer.on("icegatheringstatechange")
        def on_ice_gathering_state_change() -> None:
            if peer.iceGatheringState == "complete":
                complete.set()

        async with asyncio.timeout(10):
            await complete.wait()

    async def _wait_for_connected(
        self, peer: RTCPeerConnection, disconnected: asyncio.Event
    ) -> None:
        async with asyncio.timeout(20):
            while peer.connectionState != "connected":
                if disconnected.is_set():
                    raise ConnectionError(
                        f"SmallWebRTC connection entered {peer.connectionState}"
                    )
                await asyncio.sleep(0.05)
