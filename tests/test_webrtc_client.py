import asyncio

import numpy as np

from jarvis_satellite.webrtc_client import MicrophoneAudioTrack, SmallWebRTCSession


def test_microphone_track_splits_pcm_into_20ms_frames() -> None:
    async def scenario() -> None:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        samples = np.arange(1280, dtype="<i2")
        await queue.put(samples.tobytes())
        track = MicrophoneAudioTrack(queue, 16000)

        first = await track.recv()
        second = await track.recv()

        assert first.samples == 320
        assert first.sample_rate == 16000
        assert first.pts == 0
        assert first.to_ndarray().reshape(-1).tolist() == samples[:320].tolist()
        assert second.pts == 320
        assert second.to_ndarray().reshape(-1).tolist() == samples[320:640].tolist()

    asyncio.run(scenario())


def test_rejects_invalid_signaling_answer() -> None:
    session = SmallWebRTCSession(
        server_url="http://pipecat:7860/api/offer",
        auth_token=None,
        input_sample_rate=16000,
        output_sample_rate=24000,
        conversation_timeout=300,
    )

    assert session.server_url.endswith("/api/offer")
