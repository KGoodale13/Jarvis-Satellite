import asyncio

from jarvis_satellite.satellite import JarvisSatellite


class FakeAudio:
    def __init__(self) -> None:
        self.capture_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.started = False
        self.stopped = False

    def start(self, loop) -> None:
        self.started = True

    async def play(self, pcm: bytes, sample_rate: int, channels: int) -> None:
        pass

    async def stop(self) -> None:
        self.stopped = True


class FakeWakeDetector:
    phrase = "Hey Jarvis"

    def __init__(self) -> None:
        self.resets = 0

    def process(self, pcm: bytes) -> bool:
        return pcm == b"wake"

    def reset(self) -> None:
        self.resets += 1


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    async def run_with_timeout(self, audio_queue, play_audio, on_connected, on_speaking) -> None:
        self.calls += 1
        on_connected()
        on_speaking()
        raise asyncio.CancelledError


class FakeLeds:
    def __init__(self) -> None:
        self.states: list[str] = []

    def __getattr__(self, state):
        return lambda: self.states.append(state)


def test_wake_starts_one_conversation_and_stops_cleanly() -> None:
    async def scenario() -> None:
        audio = FakeAudio()
        session = FakeSession()
        leds = FakeLeds()
        wake_detector = FakeWakeDetector()
        satellite = JarvisSatellite(
            audio=audio,
            wake_detector=wake_detector,
            session=session,
            leds=leds,
            refractory_seconds=0,
        )

        task = asyncio.create_task(satellite.run())
        await audio.capture_queue.put(b"not-wake")
        await audio.capture_queue.put(b"wake")
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert audio.started
        assert audio.stopped
        assert session.calls == 1
        assert wake_detector.resets == 1
        assert leds.states == [
            "startup",
            "idle",
            "wake_detected",
            "processing",
            "listening",
            "speaking",
            "idle",
            "idle",
        ]

    asyncio.run(scenario())
