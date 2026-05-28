"""Mikrofon-Aufnahme mit sounddevice."""

import threading
import numpy as np
import sounddevice as sd
from src.config import SAMPLE_RATE, CHANNELS  # noqa: F401


class Recorder:
    """Nimmt Audio vom Mikrofon auf (16kHz, mono, float32 für Whisper)."""

    def __init__(self):
        self._chunks = []
        self._lock = threading.Lock()
        self._stream = None
        self.is_recording = False
        self.gain = 1.0           # Software-Verstaerkung; UI-Slider 0..4
        self._level = 0.0         # Letzter Peak-Wert (0..1) fuer VU-Meter

    def start(self):
        """Aufnahme starten."""
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self.is_recording = True

    def stop(self):
        """Aufnahme stoppen, Audio als numpy-Array zurückgeben."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.is_recording = False
        self._level = 0.0

        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio

    def get_audio_snapshot(self):
        """Gibt den bisherigen Audio-Puffer zurück OHNE die Aufnahme zu stoppen."""
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(list(self._chunks), axis=0).flatten()

    def take_chunks(self):
        """Holt alle bisherigen Audio-Chunks ab und leert den Puffer.

        Die Aufnahme läuft weiter — neue Chunks werden ab jetzt gesammelt.
        Gibt das Audio als numpy-Array zurück.
        """
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            self._chunks = []
        return audio

    def take_chunks_with_overlap(self, overlap_s=0.5):
        """Wie take_chunks, aber die letzten overlap_s Sekunden bleiben im Puffer.

        Nuetzlich fuer Hard-Cuts mitten im Redefluss — der naechste Chunk
        startet mit dem Overlap, damit Whisper den Wortanfang nicht verliert.
        """
        overlap_samples = int(overlap_s * SAMPLE_RATE)
        with self._lock:
            if not self._chunks:
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._chunks, axis=0).flatten()
            if len(audio) <= overlap_samples:
                # Zu wenig Daten fuer Overlap -> alles zurueckgeben, Puffer leer
                self._chunks = []
                return audio
            chunk_out = audio[:-overlap_samples]
            tail = audio[-overlap_samples:]
            # Tail als einzelner 2D-Chunk im Puffer behalten
            self._chunks = [tail.reshape(-1, CHANNELS)]
        return chunk_out

    def has_silence_tail(self, min_silence_s=0.6, rms_threshold=0.008):
        """Prueft, ob die letzten min_silence_s Sekunden des Puffers leise sind.

        RMS wird in 100 ms-Fenstern berechnet. Liegt jedes Fenster der letzten
        min_silence_s Sekunden unter rms_threshold, gilt das als Sprechpause.
        """
        with self._lock:
            if not self._chunks:
                return False
            # Nur die letzten (min_silence_s * SAMPLE_RATE) Samples ansehen
            needed = int(min_silence_s * SAMPLE_RATE)
            total = sum(c.shape[0] for c in self._chunks)
            if total < needed:
                return False
            # Tail zusammenbauen (nur ausreichend viel)
            collected = []
            remaining = needed
            for c in reversed(self._chunks):
                if remaining <= 0:
                    break
                if c.shape[0] >= remaining:
                    collected.append(c[-remaining:])
                    remaining = 0
                else:
                    collected.append(c)
                    remaining -= c.shape[0]
            collected.reverse()
            tail = np.concatenate(collected, axis=0).flatten()
        window = int(0.1 * SAMPLE_RATE)  # 100 ms
        if window <= 0 or len(tail) < window:
            return False
        n_win = len(tail) // window
        for i in range(n_win):
            w = tail[i * window:(i + 1) * window]
            rms = float(np.sqrt(np.mean(w * w))) if len(w) else 0.0
            if rms > rms_threshold:
                return False
        return True

    def get_level(self):
        """Aktueller Peak-Pegel (0..1) fuer VU-Meter-Anzeige."""
        return self._level

    def _callback(self, indata, frames, time, status):
        """Stream-Callback — Gain anwenden, Pegel messen, Audio sammeln."""
        amplified = indata * self.gain if self.gain != 1.0 else indata
        # Peak fuer VU-Meter (schnelle Reaktion, kein Smoothing — UI macht das)
        if amplified.size:
            self._level = float(np.max(np.abs(amplified)))
        with self._lock:
            self._chunks.append(amplified.copy())
