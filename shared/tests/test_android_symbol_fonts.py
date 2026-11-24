"""Android: Qt falls back to the system's symbol fonts. Qt for Android only
tries the fonts QT_ANDROID_FONTS names (Roboto, Droid Sans, Droid Sans
Fallback), none of which has Anki's down arrow, so the Add window showed
"History" with a box (Galaxy M30s, Android 11, 2026-11-24). The package needs
_kioku_android, so the function is taken from its source."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "android/python/kioku_platform/__init__.py"
QT_DEFAULT = "Roboto;Droid Sans;Droid Sans Fallback"


def load(environ: dict) -> dict:
    tree = ast.parse(SOURCE.read_text())
    wanted = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "_symbol_fonts")
              or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SYMBOL_FONTS" for t in n.targets))]
    assert len(wanted) == 2
    ns = {"os": type("FakeOs", (), {"environ": environ})}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def test_symbol_fonts_after_qts_own() -> None:
    environ = {"QT_ANDROID_FONTS": QT_DEFAULT}
    load(environ)["_symbol_fonts"]()
    names = environ["QT_ANDROID_FONTS"].split(";")
    assert names[:3] == QT_DEFAULT.split(";")
    assert "Noto Sans Symbols" in names[3:]


def test_twice_adds_nothing() -> None:
    environ = {"QT_ANDROID_FONTS": QT_DEFAULT}
    fn = load(environ)["_symbol_fonts"]
    fn()
    once = environ["QT_ANDROID_FONTS"]
    fn()
    assert environ["QT_ANDROID_FONTS"] == once


def test_without_qts_list() -> None:
    environ: dict = {}
    load(environ)["_symbol_fonts"]()
    assert environ["QT_ANDROID_FONTS"].split(";")[0] == "Noto Sans Symbols"


def load_symbols_file():
    tree = ast.parse(SOURCE.read_text())
    wanted = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == "symbols_file")
              or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SYMBOLS_FILE_PREFIX" for t in n.targets))]
    assert len(wanted) == 2
    ns: dict = {"Callable": object}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns["symbols_file"]


def test_fullest_symbols_file() -> None:
    # Android 11 (emulator and Galaxy M30s): Qt kept Subsetted2 (124
    # characters, no arrows) for the family
    sizes = {"NotoSansSymbols-Regular-Subsetted.ttf": 709192,
             "NotoSansSymbols-Regular-Subsetted2.ttf": 21000,
             "Roboto-Regular.ttf": 305608}
    assert load_symbols_file()(list(sizes), sizes.__getitem__) == "NotoSansSymbols-Regular-Subsetted.ttf"


def test_no_symbols_file() -> None:
    assert load_symbols_file()(["Roboto-Regular.ttf"], lambda n: 1) is None


def test_runs_before_qt() -> None:
    tree = ast.parse(SOURCE.read_text())
    prepare = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare")
    calls = [c.func.id for c in ast.walk(prepare) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]
    assert "_symbol_fonts" in calls
