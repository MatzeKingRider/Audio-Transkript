"""Screenshot-Aufnahme und OCR mit macOS Vision API."""

import subprocess
import tempfile
import os
from AppKit import NSImage
from Quartz import CGImageSourceCreateWithData, CGImageSourceCreateImageAtIndex
import Vision
from src.config import OCR_LANGUAGES


def capture_screenshot():
    """Benutzer wählt Bildschirmbereich (wie Cmd+Shift+4), gibt NSImage zurück oder None."""
    # Temporäre Datei statt Clipboard — zuverlässiger
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()

    try:
        result = subprocess.run(
            ["screencapture", "-i", tmp.name],
            timeout=60,
        )
        if result.returncode != 0:
            return None

        # Prüfe ob Datei erstellt wurde (User könnte mit Escape abbrechen)
        if not os.path.exists(tmp.name) or os.path.getsize(tmp.name) == 0:
            return None

        image = NSImage.alloc().initWithContentsOfFile_(tmp.name)
        return image
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def ocr_image(ns_image):
    """NSImage per Vision OCR zu Text umwandeln."""
    tiff_data = ns_image.TIFFRepresentation()
    if not tiff_data:
        return ""

    source = CGImageSourceCreateWithData(tiff_data, None)
    if not source:
        return ""
    cg_image = CGImageSourceCreateImageAtIndex(source, 0, None)
    if not cg_image:
        return ""

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
        cg_image, None
    )
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLanguages_(OCR_LANGUAGES)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

    success = handler.performRequests_error_([request], None)
    if not success[0]:
        return ""

    results = request.results()
    if not results:
        return ""

    lines = []
    for observation in results:
        candidate = observation.topCandidates_(1)
        if candidate:
            lines.append(candidate[0].string())

    return "\n".join(lines)
