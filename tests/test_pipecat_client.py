from jarvis_satellite.pipecat_client import PipecatSession


def test_recognizes_session_end_control_messages() -> None:
    session = PipecatSession(
        server_url="ws://example/ws",
        auth_token=None,
        input_sample_rate=16000,
        conversation_timeout=300,
    )

    assert session._is_session_end({"type": "session-ended"})
    assert session._is_session_end({"type": "conversation_end"})
    assert not session._is_session_end({"type": "bot-stopped-speaking"})
    assert not session._is_session_end("session-ended")
