"""Whisper-Transkription — mlx-whisper (Apple Silicon) oder faster-whisper (Intel)."""

import threading
import numpy as np
import re
from src.config import (
    WHISPER_BACKEND, WHISPER_MODEL, WHISPER_LANGUAGE,
    SAMPLE_RATE,
)
from src import vocabulary

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
    "raaco, boxxser, carrylite",
    "raaco boxxser, carrylite",
]


def dedupe_overlap(prev_text: str, new_text: str, max_tokens: int = 8) -> str:
    """Entfernt ueberlappende Start-Tokens aus new_text, die bereits am Ende
    von prev_text stehen. Nuetzlich fuer Audio-Chunks mit Overlap.

    Vergleicht die letzten max_tokens Worte von prev_text mit den ersten
    max_tokens Worten von new_text (case-insensitive, Satzzeichen ignoriert).
    Findet den laengsten Praefix von new_text, der als Suffix in prev_text
    vorkommt, und schneidet ihn weg.
    """
    if not prev_text or not new_text:
        return new_text

    def _norm(tok: str) -> str:
        return tok.strip(" .,;:!?\"'-").lower()

    prev_tokens = prev_text.split()
    new_tokens = new_text.split()
    if not prev_tokens or not new_tokens:
        return new_text

    prev_tail = [_norm(t) for t in prev_tokens[-max_tokens:]]
    new_head = [_norm(t) for t in new_tokens[:max_tokens]]

    # Laengsten Overlap finden: new_head[:k] == prev_tail[-k:]
    best = 0
    max_k = min(len(prev_tail), len(new_head))
    for k in range(max_k, 0, -1):
        if new_head[:k] and new_head[:k] == prev_tail[-k:]:
            best = k
            break
    if best == 0:
        return new_text
    return " ".join(new_tokens[best:])


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
        import os
        if on_progress:
            on_progress(f"Lade Whisper-Modell ({WHISPER_MODEL})...")
        cpu_threads = min(8, os.cpu_count() or 4)
        self._model = WhisperModel(
            WHISPER_MODEL, device="cpu", compute_type="int8",
            cpu_threads=cpu_threads, num_workers=1,
        )

    def transcribe(self, audio, prev_text: str = "", language: str = None):
        """Audio transkribieren. Gibt (text, language) zurueck.

        prev_text: letzter Transkript-Ausschnitt, wird (gekuerzt) als
        zusaetzlicher Kontext an den initial_prompt angehaengt — sorgt
        fuer logische Verkettung aufeinanderfolgender kurzer Sequenzen.

        language: ISO-Code ("de", "en", ...) — ueberschreibt die Config-Default.
        Fehlt der Wert, wird WHISPER_LANGUAGE aus config benutzt.
        """
        if language is None:
            language = WHISPER_LANGUAGE
        if not self.model_loaded:
            return "", "?"

        # Zu kurzes Audio ignorieren (< 0.5 Sek. = Halluzinationsrisiko / zu wenig Signal)
        if len(audio) < int(SAMPLE_RATE * 0.5):
            return "", "?"

        # Stille am Ende trimmen (reduziert Halluzinationen massiv)
        audio = self._trim_silence(audio)
        if len(audio) < int(SAMPLE_RATE * 0.5):
            return "", "?"

        prompt = self._build_prompt(prev_text)

        with self._lock:
            if WHISPER_BACKEND == "mlx":
                text, lang = self._transcribe_mlx(audio, prompt, language)
            else:
                text, lang = self._transcribe_faster(audio, prompt, language)

        text = self._filter_hallucinations(text)
        if not text:
            return "", lang
        text = self._fix_spacing(text)

        return text, lang

    @staticmethod
    def _build_prompt(prev_text: str) -> str:
        """Initial-Prompt = gepflegte Begriffe + letzte ~200 Zeichen vom vorigen Chunk."""
        base = vocabulary.prompt_terms()
        if not prev_text:
            return base
        tail = prev_text.strip()
        if len(tail) > 200:
            tail = tail[-200:]
        return f"{base} {tail}".strip()

    @staticmethod
    def _fix_spacing(text):
        """Nachbearbeitung: Leerzeichen nach Satzzeichen, Wort-Korrekturen."""
        # Leerzeichen nach Satzzeichen wenn Buchstabe folgt
        text = re.sub(r'([.!?;:,])([A-Za-zÄÖÜäöüß])', r'\1 \2', text)
        # Leerzeichen nach letztem Satzzeichen anfuegen
        # (damit nachfolgende Aufnahmen nicht am Satzzeichen kleben)
        if text and text[-1] in '.!?;:,':
            text += ' '
        # Wort-Korrekturen (case-insensitive, nur ganze Woerter).
        # Callable-Ersatz, damit Sonderzeichen im "richtig"-Text nicht als
        # Regex-Backreference interpretiert werden.
        for wrong, right in vocabulary.corrections().items():
            pattern = r'\b' + re.escape(wrong) + r'\b'
            text = re.sub(pattern, lambda m, r=right: r, text,
                          flags=re.IGNORECASE)
        return text

    @staticmethod
    def _filter_hallucinations(text):
        """Entfernt bekannte Whisper-Halluzinationen."""
        # Trailing "..." ist ein Whisper-Ende-Token, kein gesprochener Inhalt.
        # Entfernen, damit das Satzende sauber bleibt (ggf. mit echtem Punkt ersetzen).
        text = re.sub(r'\s*\.{3,}\s*$', '.', text.rstrip())
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

    @staticmethod
    def _trim_silence(audio, threshold=0.004):
        """Stille am Ende des Audio-Arrays entfernen.

        Whisper halluziniert wenn am Ende Stille ist — aber wir wollen lieber
        zu wenig wegschneiden als das Satzende zu verlieren.
        """
        # Von hinten nach vorn: erstes Sample ueber Schwelle finden
        abs_audio = np.abs(audio)
        # In 160-Sample-Bloecken (10ms) pruefen
        block_size = 160
        n_blocks = len(abs_audio) // block_size
        for i in range(n_blocks - 1, -1, -1):
            block = abs_audio[i * block_size:(i + 1) * block_size]
            if np.max(block) > threshold:
                # 0.6 Sek. Puffer nach letztem Ton lassen, damit leise
                # Satzendungen ("...", abklingende Konsonanten) nicht verloren gehen
                end = min(len(audio), (i + 1) * block_size + int(
                    SAMPLE_RATE * 0.6))
                return audio[:end]
        return audio

    def _transcribe_mlx(self, audio, prompt: str, language: str):
        import mlx_whisper
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=WHISPER_MODEL,
            language=language,
            initial_prompt=prompt,
            condition_on_previous_text=True,
            no_speech_threshold=0.4,
            compression_ratio_threshold=2.0,
        )
        return result.get("text", "").strip(), result.get("language", language or "?")

    def _transcribe_faster(self, audio, prompt: str, language: str):
        segments, info = self._model.transcribe(
            audio,
            language=language,
            initial_prompt=prompt,
            condition_on_previous_text=True,
            no_speech_threshold=0.4,
            compression_ratio_threshold=2.0,
            beam_size=1,
            best_of=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        lang = getattr(info, "language", language) or language or "?"
        return text, lang

    def transcribe_quick(self, audio):
        """Schnelle Zwischen-Transkription fuer Live-Preview."""
        if not self.model_loaded:
            return ""
        if len(audio) < SAMPLE_RATE:
            return ""
        if not self._lock.acquire(blocking=False):
            return ""
        try:
            prompt = vocabulary.prompt_terms()
            if WHISPER_BACKEND == "mlx":
                text, _ = self._transcribe_mlx(audio, prompt, WHISPER_LANGUAGE)
            else:
                text, _ = self._transcribe_faster(audio, prompt, WHISPER_LANGUAGE)
            return text
        finally:
            self._lock.release()
