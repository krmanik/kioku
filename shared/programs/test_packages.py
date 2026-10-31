"""Test the native Python packages bundled for add-ons
(shared/tools/build_wheels.sh) inside the app: run test(tmp_dir) from
devcmd, or python3 test_packages.py on a machine that has them."""

import io
import os
import sys


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name + (f": {detail}" if detail and not condition else ""))
    return bool(condition)


def test(tmp):
    results = []

    def ok(*a):
        results.append(check(*a))

    def attempt(name, fn):
        try:
            fn()
        except Exception as e:
            ok(name, False, f"{type(e).__name__}: {e}")

    def numpy_():
        import numpy as np

        a = np.arange(12, dtype=float).reshape(3, 4)
        ok("numpy arrays", a.sum() == 66 and a.T.shape == (4, 3))
        m = np.array([[2.0, 1.0], [1.0, 3.0]])
        ok("numpy.linalg (lapack_lite)", np.allclose(np.linalg.inv(m) @ m, np.eye(2)))
        ok("numpy.fft", np.allclose(np.fft.ifft(np.fft.fft([1, 2, 3])).real, [1, 2, 3]))
        ok("numpy.random", np.random.default_rng(1).integers(0, 10, 5).shape == (5,))

    def pillow():
        from PIL import Image, ImageDraw, ImageFont, features

        img = Image.new("RGB", (64, 48), "white")
        ImageDraw.Draw(img).rectangle((8, 8, 40, 30), fill="red")
        for fmt in ("PNG", "JPEG", "WEBP", "GIF"):
            buf = io.BytesIO()
            img.save(buf, fmt)
            buf.seek(0)
            ok(f"Pillow {fmt}", Image.open(buf).size == (64, 48))
        ok("Pillow FreeType", features.check("freetype2"))
        font = ImageFont.load_default(size=14)
        ok("Pillow text", ImageDraw.Draw(img).textlength("Kioku", font=font) > 10)
        img.thumbnail((32, 32))
        ok("Pillow resize", img.size[0] <= 32)

    def crypto():
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from OpenSSL import crypto as ossl

        f = Fernet(Fernet.generate_key())
        ok("cryptography Fernet", f.decrypt(f.encrypt(b"kioku")) == b"kioku")
        h = hashes.Hash(hashes.SHA256())
        h.update(b"x")
        ok("cryptography hashes", len(h.finalize()) == 32)
        key = ossl.PKey()
        key.generate_key(ossl.TYPE_RSA, 2048)
        ok("pyOpenSSL key", key.bits() == 2048)

    def jieba_():
        import jieba

        jieba.setLogLevel(60)
        ok("jieba", list(jieba.cut("我来到北京清华大学")) == ["我", "来到", "北京", "清华大学"])

    for name, fn in (("numpy", numpy_), ("Pillow", pillow), ("cryptography", crypto),
                     ("jieba", jieba_)):
        attempt(name, fn)
    failed = results.count(False)
    print(f"{len(results) - failed}/{len(results)} passed")
    return failed == 0


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sys.exit(0 if test(tmp) else 1)
