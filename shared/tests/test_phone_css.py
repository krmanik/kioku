"""PHONE_CSS picks the deck list and the top bar with :has(), which
WebViews before Chrome 105 don't know (Android 11's built-in WebView 87):
each such rule comes again with classes that VIEWPORT sets there
(kioku.webscripts)."""

from __future__ import annotations

import re

from kioku import webscripts


def test_every_has_rule_has_a_class_twin() -> None:
    css = webscripts.PHONE_CSS
    assert "$" not in css
    has_rules = re.findall(r"[^{}]*:has\([^{}]*\{[^}]*\}", css)
    assert has_rules
    for rule in has_rules:
        body = rule[rule.index("{"):]
        twins = [r for r in re.findall(r"[^{}]*\{[^}]*\}", css)
                 if r[r.index("{"):] == body and ":has(" not in r]
        assert twins, rule


def test_viewport_sets_the_classes() -> None:
    for selector in webscripts._MARKED.values():
        for name in re.findall(r"\.(kioku-[\w-]+)", selector):
            assert f'"{name}"' in webscripts.VIEWPORT, name
