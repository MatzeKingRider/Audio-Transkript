"""Whisper-Transkription mit mlx-whisper."""

import threading
import numpy as np
import mlx_whisper
from src.config import WHISPER_MODEL, WHISPER_LANGUAGE, SAMPLE_RATE


class Transcriber:
    """Lädt das Whisper-Modell und transkribiert Audio."""

    def __init__(self):
        self.model_loaded = False
        self._loading = False

    def load_model(self, on_progress=None, on_done=None):
        """Modell im Hintergrund laden."""
        if self.model_loaded or self._loading:
            return
        self._loading = True

        def _load():
            try:
                if on_progress:
                    on_progress("Lade Whisper-Modell...")
                # Dummy-Transkription erzwingt Modell-Download und -Laden
                dummy = np.zeros(16000, dtype=np.float32)
                mlx_whisper.transcribe(
                    dummy, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
                )
                self.model_loaded = True
                if on_done:
                    on_done()
            except Exception as e:
                if on_progress:
                    on_progress(f"Modellfehler: {e}")
            finally:
                self._loading = False

        threading.Thread(target=_load, daemon=True).start()

    def transcribe(self, audio):
        """Audio-Array transkribieren, gibt Text zurück."""
        if not self.model_loaded:
            return "[Modell noch nicht geladen]"

        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
        )
        return result.get("text", "").strip()

    def transcribe_quick(self, audio):
        """Schnelle Zwischen-Transkription für Live-Preview."""
        if not self.model_loaded:
            return ""
        # Mindestens 1 Sekunde Audio für sinnvolles Ergebnis
        if len(audio) < SAMPLE_RATE:
            return ""
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
        )
        return result.get("text", "").strip()
