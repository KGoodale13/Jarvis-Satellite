"""Local microWakeWord detection."""

from __future__ import annotations

from pathlib import Path

from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures


class MicroWakeWordDetector:
    def __init__(self, config_path: Path) -> None:
        self._model = MicroWakeWord.from_config(config_path=config_path)
        self._features = MicroWakeWordFeatures()

    @property
    def phrase(self) -> str:
        return self._model.wake_word

    def process(self, pcm: bytes) -> bool:
        return any(
            self._model.process_streaming(features)
            for features in self._features.process_streaming(pcm)
        )

    def reset(self) -> None:
        self._model.reset()
        self._features.reset()
