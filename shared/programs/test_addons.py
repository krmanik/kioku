"""Exercise real add-ons' own code that starts bundled programs, inside the
app (devcmd): Japanese Support (mecab, kakasi), AJT Media Converter
(ffmpeg) and AnkiOCR (tesseract through pytesseract). Install them in
addons21 first; run test(tmp_dir, ocr_image)."""

import os
import shutil
import sys


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name + (f": {detail}" if detail and not condition else ""))
    return bool(condition)


def test(tmp, ocr_image):
    from aqt import mw

    results = []

    def ok(*a):
        results.append(check(*a))

    def attempt(name, fn):
        if name not in sys.modules:
            ok(f"{name} loaded", False, "not loaded (installed in addons21?)")
            return
        try:
            fn()
        except Exception as e:
            import traceback

            traceback.print_exc()
            ok(name, False, f"{type(e).__name__}: {e}")

    def japanese():
        reading = sys.modules["3918629684.reading"]
        mecab = reading.MecabController()
        out = mecab.reading("日本語を勉強します")
        ok("Japanese Support: mecab reading", "日本語[にほんご]" in out and "勉強[べんきょう]" in out, out)
        out = mecab.reading("東京")
        ok("Japanese Support: mecab again (same process)", "東京[とうきょう]" in out, out)
        kakasi = reading.KakasiController()
        out = kakasi.reading("カタカナ")
        ok("Japanese Support: kakasi", out == "かたかな", out)

    def ajt():
        from PIL import Image

        fc = sys.modules["1151815987.file_converters.file_converter"]
        ok("AJT: finds ffmpeg", bool(fc.find_ffmpeg_exe()))
        src = os.path.join(tmp, "ajt.png")
        Image.new("RGB", (320, 200), "blue").save(src)
        dst = os.path.join(tmp, "ajt.webp")
        config = sys.modules["1151815987.config"].MediaConverterConfig()
        fc.FileConverter(src, dst, config).convert()
        ok("AJT: image to webp", os.path.getsize(dst) > 0 and open(dst, "rb").read(12)[8:12] == b"WEBP")
        wav = os.path.join(tmp, "ajt.wav")
        import subprocess

        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=1", wav], capture_output=True)
        dst = os.path.join(tmp, "ajt.ogg")
        fc.FileConverter(wav, dst, config).convert()
        ok("AJT: audio to opus/ogg", os.path.exists(dst) and open(dst, "rb").read(4) == b"OggS")

    def ankiocr():
        ocr = sys.modules["450181164.ocr"]
        # its own --tessdata-dir: the AnkiWeb package has eng.traineddata there
        eng = os.path.join(str(ocr.TESSDATA_DIR), "eng.traineddata")
        if not os.path.exists(eng):
            os.makedirs(str(ocr.TESSDATA_DIR), exist_ok=True)
            shutil.copy(os.path.join(os.environ["TESSDATA_PREFIX"], "eng.traineddata"), eng)
        reader = ocr.OCR(col=mw.col, languages=["eng"], use_multithreading=True, num_threads=2)
        text = reader._ocr_img(ocr_image, 1, ["eng"]) if hasattr(reader, "_ocr_img") else ""
        if not isinstance(text, str):
            text = str(text)
        ok("AnkiOCR: tesseract through pytesseract", len(text.split()) > 50, text[:200])

    attempt("3918629684", japanese)
    attempt("1151815987", ajt)
    # AnkiOCR's GUI imports PyQt5 (fails on Qt 6 Anki anywhere): its OCR
    # module alone, without the package's __init__
    if "450181164" not in sys.modules:
        import types

        package = types.ModuleType("450181164")
        package.__path__ = [os.path.join(mw.addonManager.addonsFolder(), "450181164")]
        sys.modules["450181164"] = package
    try:
        __import__("450181164.ocr")
    except Exception as e:
        ok("AnkiOCR's ocr module", False, f"{type(e).__name__}: {e}")
    attempt("450181164.ocr", ankiocr)
    failed = results.count(False)
    print(f"{len(results) - failed}/{len(results)} passed")
    return failed == 0
