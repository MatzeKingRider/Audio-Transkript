"""Whisper-Transkription mit mlx-whisper."""

import threading
import numpy as np
import mlx_whisper
from src.config import WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_PROMPT, SAMPLE_RATE


class Transcriber:
    """Lädt das Whisper-Modell und transkribiert Audio."""

    def __init__(self):
        self.model_loaded = False
        self._loading = False
        self._lock = threading.Lock()

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
        """Audio-Array transkribieren. Default: Deutsch, Fallback: Auto-Erkennung.

        Erst mit language=de transkribieren. Falls das Ergebnis nach
        Halluzination aussieht (bekannte Whisper-Artefakte bei Stille),
        wird das Ergebnis verworfen.
        """
        if not self.model_loaded:
            return "", "?"

        # Bekannte Whisper-Halluzinationen bei Stille/Rauschen
        hallucinations = {
            "vielen dank fürs zusehen",
            "vielen dank fürs zuschauen",
            "thank you for watching",
            "thanks for watching",
            "untertitel von",
            "untertitelung",
            "copyright",
            "subtitles by",
        }

        with self._lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=WHISPER_MODEL,
                language=WHISPER_LANGUAGE,
                initial_prompt=WHISPER_PROMPT,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
            )
        text = result.get("text", "").strip()

        # Halluzinationen filtern
        if text.lower().rstrip(".!") in hallucinations:
            return "", "de"

        return text, "de"

    def transcribe_quick(self, audio):
        """Schnelle Zwischen-Transkription für Live-Preview."""
        if not self.model_loaded:
            return ""
        if len(audio) < SAMPLE_RATE:
            return ""
        # Non-blocking: wenn gerade eine andere Transkription läuft, überspringen
        if not self._lock.acquire(blocking=False):
            return ""
        try:
            result = mlx_whisper.transcribe(
                audio, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE, initial_prompt=WHISPER_PROMPT
            )
            return result.get("text", "").strip()
        finally:
            self._lock.release()
