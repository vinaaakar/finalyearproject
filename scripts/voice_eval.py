#!/usr/bin/env python3
"""Speech-recognition evaluation for Scout and Maple (Phase H). Local only: whisper.cpp + macOS voices; nothing is uploaded.

Two modes, both using the same engine code as the stores (backend/app/speech/adapters.py):

  1. Real recordings (the physical-microphone workflow, docs/voice-testing.md):
       backend/.venv/bin/python scripts/voice_eval.py --recordings DIR
     DIR holds WAV/M4A files plus a manifest.csv:  file,language,expected_text[,speaker,conditions]
     e.g.  ta_tent_quiet.m4a,ta,உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?,native-ta-1,quiet room laptop mic

  2. Synthetic stress test (macOS voices Vani / Rishi / Lekha, with added background noise):
       backend/.venv/bin/python scripts/voice_eval.py --synthetic [--snr 30 15 5] [--set demo]
     --set demo adds the demonstration-script sentences (9 per language instead of 4).

Reports, per utterance: detected language and probability, whether the engine asked for clarification (uncertain),
character error rate against the expected text, and a summary per language and condition. Synthetic speech is NOT a
substitute for real speakers: it only shows how the pipeline degrades with noise.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import struct
import subprocess
import sys
import statistics
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

PHRASES = {
    "ta": ["உங்களிடம் இரண்டு பேர் தங்கும் கூடாரம் இருக்கிறதா?", "திருப்பி அனுப்பும் கொள்கை என்ன?", "என் ஆர்டர் எங்கே இருக்கிறது?",
           "ஷிப்பிங் கட்டணம் எவ்வளவு?"],
    "en": ["Do you have a two person tent?", "What is your return policy?", "Where is my order?", "How much is shipping?"],
    "hi": ["क्या आपके पास दो लोगों का टेंट है?", "आपकी वापसी नीति क्या है?", "मेरा ऑर्डर कहाँ है?", "शिपिंग कितनी है?"],
}
# --set demo adds the sentences of the final demonstration script (docs/demo-guide.md) to the basic four per language.
DEMO_PHRASES = {
    "ta": ["மிகவும் மலிவான தூங்கும் பை எது?", "இரண்டு பேருக்கு பத்தாயிரம் ரூபாய்க்குள் கூடாரம் இருக்கிறதா?",
           "எனக்கு தவறான பொருள் வந்துள்ளது", "எனக்கு மனித உதவி வேண்டும்", "எனது புகார் நிலை என்ன?"],
    "en": ["What's the cheapest sleeping bag?", "Compare the French press and the pour-over dripper",
           "Add it to my cart", "I want to request a refund", "What did I pay for my last order?"],
    "hi": ["सबसे सस्ती चाय कौन सी है?", "इसका वज़न कितना है?", "मुझे अपना सामान वापस करना है",
           "मुझे किसी इंसान से बात करनी है", "मेरी शिकायत की स्थिति क्या है?"],
}
VOICES = {"ta": "Vani", "en": "Rishi", "hi": "Lekha"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    return "".join(ch for ch in s if ch.isalnum() or unicodedata.category(ch).startswith("M"))


def cer(ref: str, hyp: str) -> float:
    """Character error rate (Levenshtein distance / reference length) after removing spaces and punctuation."""
    r, h = norm(ref), norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i]
        for j, hc in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return round(prev[-1] / len(r), 3)


def to_wav16k(src: Path, dst: Path) -> None:
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(src), str(dst)], check=True, capture_output=True)


def add_noise(wav_in: Path, wav_out: Path, snr_db: float, seed: int) -> None:
    """Mix white noise at the given signal-to-noise ratio (only over the speech's own average power)."""
    with wave.open(str(wav_in)) as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    power = sum(x * x for x in samples) / max(1, len(samples))
    noise_rms = (power / (10 ** (snr_db / 10))) ** 0.5
    rnd = random.Random(seed)
    mixed = [max(-32768, min(32767, int(x + rnd.gauss(0, noise_rms)))) for x in samples]
    with wave.open(str(wav_out), "wb") as w:
        w.setparams(params)
        w.writeframes(struct.pack(f"<{len(mixed)}h", *mixed))


def engine():
    from app.config import load_settings
    from app.speech.adapters import WhisperCppSTT

    s = load_settings()
    stt = WhisperCppSTT(s.whisper_cpp_bin, s.whisper_model_path, en_model_path=s.whisper_en_model_path,
                        languages=s.speech_languages, default_language=s.speech_default_language)
    if not (stt.available and stt.multilingual):
        sys.exit("A multilingual whisper.cpp model is required (scripts/setup_speech_models.sh, docs/voice.md).")
    return stt


def run_one(stt, wav: Path, lang: str, expected: str, **meta) -> dict:
    started = time.perf_counter()
    t = stt.recognize(wav.read_bytes(), "audio/wav", "auto")
    seconds = round(time.perf_counter() - started, 3)       # local whisper.cpp recognition time for this recording
    return {**meta, "seconds": seconds, "expected_language": lang, "detected": t.detected_language, "probability": round(t.language_probability or 0, 2),
            "uncertain": t.uncertain, "language_ok": (t.language == lang) and not t.uncertain, "clarified": t.uncertain,
            "cer": cer(expected, t.text), "heard": t.text, "expected": expected}


def synthetic(stt, snrs: list[float], phrase_set: str = "basic") -> list[dict]:
    rows = []
    sets = {lang: PHRASES[lang] + (DEMO_PHRASES[lang] if phrase_set == "demo" else []) for lang in PHRASES}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for lang, phrases in sets.items():
            for i, text in enumerate(phrases):
                aiff, clean = tmp / f"{lang}{i}.aiff", tmp / f"{lang}{i}.wav"
                subprocess.run(["say", "-v", VOICES[lang], "-o", str(aiff), text], check=True)
                to_wav16k(aiff, clean)
                rows.append(run_one(stt, clean, lang, text, condition="clean", voice=VOICES[lang]))
                for snr in snrs:
                    noisy = tmp / f"{lang}{i}_snr{snr}.wav"
                    add_noise(clean, noisy, snr, seed=i)
                    rows.append(run_one(stt, noisy, lang, text, condition=f"noise {snr:g} dB SNR", voice=VOICES[lang]))
    return rows


def recordings(stt, directory: Path) -> list[dict]:
    rows = []
    with open(directory / "manifest.csv", newline="", encoding="utf-8") as f, tempfile.TemporaryDirectory() as tmp:
        for rec in csv.DictReader(f):
            src = directory / rec["file"]
            wav = Path(tmp) / (src.stem + ".wav")
            to_wav16k(src, wav)
            rows.append(run_one(stt, wav, rec["language"], rec["expected_text"], file=rec["file"],
                                speaker=rec.get("speaker", ""), condition=rec.get("conditions", "")))
    return rows


def summary(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["expected_language"], r.get("condition", "")), []).append(r)
    out = []
    for (lang, cond), rs in sorted(groups.items()):
        wrong = [r for r in rs if not r["language_ok"] and not r["clarified"]]
        out.append({"language": lang, "condition": cond, "n": len(rs),
                    "language_correct": sum(r["language_ok"] for r in rs), "asked_to_clarify": sum(r["clarified"] for r in rs),
                    "wrong_language_answered": len(wrong), "mean_cer": round(sum(r["cer"] for r in rs) / len(rs), 3),
                    "median_s": round(statistics.median(r["seconds"] for r in rs), 3),
                    "p90_s": sorted(r["seconds"] for r in rs)[min(len(rs) - 1, round(0.9 * (len(rs) - 1)))]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--synthetic", action="store_true")
    g.add_argument("--recordings", type=Path)
    ap.add_argument("--snr", type=float, nargs="*", default=[30, 15, 5])
    ap.add_argument("--json", type=Path, help="write all rows here")
    ap.add_argument("--set", choices=("basic", "demo"), default="basic", help="demo: also the demonstration-script sentences")
    args = ap.parse_args()
    stt = engine()
    rows = synthetic(stt, args.snr, args.set) if args.synthetic else recordings(stt, args.recordings)
    if args.json:
        args.json.write_text(json.dumps({"rows": rows, "summary": summary(rows)}, ensure_ascii=False, indent=2))
    print(f"{'lang':4} {'condition':22} {'n':>3} {'lang ok':>7} {'clarify':>7} {'WRONG':>5} {'CER':>6} {'med s':>6} {'p90 s':>6}")
    for s in summary(rows):
        print(f"{s['language']:4} {s['condition'][:22]:22} {s['n']:>3} {s['language_correct']:>7} {s['asked_to_clarify']:>7} "
              f"{s['wrong_language_answered']:>5} {s['mean_cer']:>6} {s['median_s']:>6} {s['p90_s']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
