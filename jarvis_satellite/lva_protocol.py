"""Jarvis-specific Linux Voice Assistant protocol hooks."""

from __future__ import annotations

import logging
from typing import ClassVar, Optional

from aioesphomeapi.model import VoiceAssistantEventType, VoiceAssistantTimerEventType
from linux_voice_assistant.satellite import VoiceSatelliteProtocol

from .led_controller import JarvisLedController

_LOGGER = logging.getLogger(__name__)


class JarvisVoiceSatelliteProtocol(VoiceSatelliteProtocol):
    """Inject ReSpeaker LED handling into Linux Voice Assistant."""

    _configured_xvf_path: ClassVar[Optional[str]] = None
    _configured_disable_leds: ClassVar[bool] = False

    @classmethod
    def configure(cls, xvf_path: str | None, disable_leds: bool = False) -> None:
        cls._configured_xvf_path = xvf_path
        cls._configured_disable_leds = disable_leds

    def __init__(self, state) -> None:
        super().__init__(state)
        self._leds = self._create_led_controller()
        if self._leds is not None:
            self._leds.startup()

    def _create_led_controller(self) -> Optional[JarvisLedController]:
        if self._configured_disable_leds:
            _LOGGER.info("Jarvis LED integration disabled")
            return None

        if not self._configured_xvf_path:
            _LOGGER.info("Jarvis LED integration disabled because no XVF path was set")
            return None

        try:
            return JarvisLedController(self._configured_xvf_path)
        except FileNotFoundError:
            _LOGGER.warning(
                "Jarvis LED integration disabled because the XVF host binary was not found: %s",
                self._configured_xvf_path,
            )
        except Exception:
            _LOGGER.exception("Jarvis LED integration disabled after initialization failure")

        return None

    def process_packet(self, msg_type: int, packet_data: bytes) -> None:
        was_connected = self.state.connected
        super().process_packet(msg_type, packet_data)
        if (not was_connected) and self.state.connected and self._leds is not None:
            self._leds.connected()

    def handle_voice_event(
        self, event_type: VoiceAssistantEventType, data: dict[str, str]
    ) -> None:
        super().handle_voice_event(event_type, data)
        if self._leds is None:
            return

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_START:
            self._leds.processing()
        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            self._leds.voice_captured()
        elif (
            event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END
            and not self._continue_conversation
            and not self._tts_played
        ):
            self._refresh_idle_led()

    def handle_timer_event(
        self, event_type: VoiceAssistantTimerEventType, msg
    ) -> None:
        super().handle_timer_event(event_type, msg)
        if self._leds is None:
            return

        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            self._leds.processing()

    def wakeup(self, wake_word) -> None:
        was_pipeline_active = self._pipeline_active
        was_timer_finished = self._timer_finished
        super().wakeup(wake_word)
        if self._leds is None:
            return

        if was_timer_finished and not self._timer_finished:
            self._refresh_idle_led()
        elif (not was_pipeline_active) and self._pipeline_active:
            self._leds.wake_detected()

    def _on_wakeup_sound_finished(self, wake_word_phrase: str) -> None:
        if self._leds is not None:
            self._leds.listening()
        super()._on_wakeup_sound_finished(wake_word_phrase)

    def play_tts(self) -> None:
        if self._leds is not None:
            self._leds.speaking()
        super().play_tts()

    def _tts_finished(self) -> None:
        super()._tts_finished()
        if self._leds is None:
            return

        if self._continue_conversation:
            self._leds.listening()
        else:
            self._refresh_idle_led()

    def stop(self) -> None:
        super().stop()
        self._refresh_idle_led()

    def _set_muted(self, new_state: bool) -> None:
        super()._set_muted(new_state)
        if self._leds is None:
            return

        if self.state.muted:
            self._leds.muted()
        else:
            self._refresh_idle_led()

    def connection_lost(self, exc) -> None:
        super().connection_lost(exc)
        if self._leds is not None:
            self._leds.disconnected()

    def _refresh_idle_led(self) -> None:
        if self._leds is None:
            return

        if self.state.muted:
            self._leds.muted()
        elif self.state.connected:
            self._leds.idle()
        else:
            self._leds.disconnected()
