"""Whisper-Transkription — mlx-whisper (Apple Silicon) oder faster-whisper (Intel)."""

import threading
import numpy as np
from src.config import (
    WHISPER_BACKEND, WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_PROMPT, SAMPLE_RATE,
)

# Whisper halluziniert diese Phrasen bei Stille, Rauschen oder Aufnahme-Ende.
# Exakte Matches (nach lowercase + strip von Satzzeichen):
HALLUCINATION_EXACT = {
    "vielen dank fürs zusehen",
    "vielen dank fürs zuschauen",
    "vielen dank für ihre aufmerksamkeit",
    "vielen dank",
    "danke fürs zusehen",
    "danke fürs zuschauen",
    "danke für ihre aufmerksamkeit",
    "danke schön",
    "thank you for watching",
    "thanks for watching",
    "thank you",
    "untertitel von",
    "untertitelung",
    "untertitel der amara.org-community",
    "copyright",
    "subtitles by",
    "sous-titrage",
    "bis zum nächsten mal",
    "bis zum nächsten video",
    "tschüss",
}

# Teilstrings — wenn der GESAMTE Text nur daraus besteht, ist es Halluzination:
HALLUCINATION_CONTAINS = [
    "vielen dank fürs",
    "vielen dank für's",
    "vielen dank fur",
    "danke fürs zu",
    "danke für's zu",
    "danke für ihre aufmerksamkeit",
    "thank you for watching",
    "thanks for watching",
    "untertitel von",
    "untertitel der",
    "subtitles by",
    "sous-titres",
    "amara.org",
]

# Phrasen die am ENDE eines echten Textes angehaengt werden — werden abgeschnitten:
HALLUCINATION_SUFFIXES = [
    "vielen dank fürs zusehen",
    "vielen dank für's zusehen",
    "vielen dank fürs zuschauen",
    "vielen dank für's zuschauen",
    "vielen dank für ihre aufmerksamkeit",
    "vielen dank",
    "danke fürs zusehen",
    "danke für's zusehen",
    "danke fürs zuschauen",
    "danke für's zuschauen",
    "danke für ihre aufmerksamkeit",
    "thank you for watching",
    "thanks for watching",
    "bis zum nächsten mal",
    "bis zum nächsten video",
]


class Transcriber:
    """Laedt das Whisper-Modell und transkribiert Audio."""

    def __init__(self):
        self.model_loaded = False
        self._loading = False
        self._lock = threading.Lock()
        self._model = None  # nur fuer faster-whisper

    def load_model(self, on_progress=None, on_done=None):
        """Modell im Hintergrund laden."""
        if self.model_loaded or self._loading:
            return
        self._loading = True

        def _load():
            try:
                if on_progress:
                    on_progress("Lade Whisper-Modell...")

                if WHISPER_BACKEND == "mlx":
                    self._load_mlx()
                else:
                    self._load_faster(on_progress)

                self.model_loaded = True
                if on_done:
                    on_done()
            except Exception as e:
                if on_progress:
                    on_progress(f"Modellfehler: {e}")
            finally:
                self._loading = False

        threading.Thread(target=_load, daemon=True).start()

    def _load_mlx(self):
        import mlx_whisper
        dummy = np.zeros(16000, dtype=np.float32)
        mlx_whisper.transcribe(
            dummy, path_or_hf_repo=WHISPER_MODEL, language=WHISPER_LANGUAGE
        )

    def _load_faster(self, on_progress=None):
        from faster_whisper import WhisperModel
        if on_progress:
            on_progress(f"Lade Whisper-Modell ({WHISPER_MODEL})...")
        self._model = WhisperModel(
            WHISPER_MODEL, device="cpu", compute_type="int8"
        )

    def transcribe(self, audio):
        """Audio transkribieren. Gibt (text, language) zurueck."""
        if not self.model_loaded:
            return "", "?"

        with self._lock:
            if WHISPER_BACKEND == "mlx":
                text = self._transcribe_mlx(audio)
            else:
                text = self._transcribe_faster(audio)

        text = self._filter_hallucinations(text)
        if not text:
            return "", "de"
        text = self._fix_spacing(text)

        return text, "de"

    @staticmethod
    def _fix_spacing(text):
        """Stellt sicher, dass nach Satzzeichen ein Leerzeichen steht."""
        import re
        # Nach . ! ? : ; ein Leerzeichen einfuegen wenn direkt ein Buchstabe folgt
        text = re.sub(r'([.!?;:,])([A-Za-zÄÖÜäöüß])', r'\1 \2', text)
        return text

    @staticmethod
    def _filter_hallucinations(text):
        """Entfernt bekannte Whisper-Halluzinationen."""
        lower = text.lower().strip().rstrip(".!?")
        # Exakter Match — gesamter Text ist Halluzination
        if lower in HALLUCINATION_EXACT:
            return ""
        # Teilstring-Match — gesamter Text ist Halluzination
        for pattern in HALLUCINATION_CONTAINS:
            if pattern in lower:
                return ""
        # Suffix-Match — Halluzination am Ende eines echten Textes abschneiden
        for suffix in HALLUCINATION_SUFFIXES:
            idx = lower.rfind(suffix)
            if idx > 0:
                text = text[:idx].rstrip(" .,;!?-")
        # Sehr kurzer Text mit nur Satzzeichen/Whitespace
        cleaned = text.replace(".", "").replace(",", "").strip()
        if len(cleaned) < 3:
            return ""
        return text.strip()

    def _transcribe_mlx(self, audio):
        import mlx_whisper
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=WHISPER_MODEL,
            language=WHISPER_LANGUAGE,
            initial_prompt=WHISPER_PROMPT,
            condition_on_previous_text=True,
            no_speech_threshold=0.6,
        )
        return result.get("text", "").strip()

    def _transcribe_faster(self, audio):
        segments, _info = self._model.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            initial_prompt=WHISPER_PROMPT,
            condition_on_previous_text=True,
            no_speech_threshold=0.6,
            beam_size=5,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def transcribe_quick(self, audio):
        """Schnelle Zwischen-Transkription fuer Live-Preview."""
        if not self.model_loaded:
            return ""
        if len(audio) < SAMPLE_RATE:
            return ""
        if not self._lock.acquire(blocking=False):
            return ""
        try:
            if WHISPER_BACKEND == "mlx":
                return self._transcribe_mlx(audio)
            else:
                return self._transcribe_faster(audio)
        finally:
            self._lock.release()
