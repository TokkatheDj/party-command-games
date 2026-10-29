#!/usr/bin/env python3
"""identity_count.py - do the generated apps still all look and sound the same? (29 Oct 2026)

Before the IDENTITY block went into the routines, 628 October apps were 48% Segoe UI,
86% gradient backgrounds and 78% plain-oscillator sound. This counts the same things for
the apps made on or after a date, plus how many carry the [style: / sound:] tag.

    python identity_count.py 2026-10-31      apps whose file name starts with that date or later
"""
import collections, glob, re, sys

since = sys.argv[1] if len(sys.argv) > 1 else "2026-10-01"
apps = [f for f in glob.glob("**/20??-??-??-*.html", recursive=True)
        if not f.startswith(("_", "node_modules")) and re.search(r"(\d{4}-\d\d-\d\d)-", f).group(1) >= since]
font, style, sound = collections.Counter(), collections.Counter(), collections.Counter()
gradient = sine_only = tagged = 0
for f in apps:
    s = open(f, encoding="utf-8", errors="ignore").read()
    m = re.findall(r"font-family:\s*([^;}{]+)", s)
    font[m[0].split(",")[0].strip(" '\"") if m else "none"] += 1
    gradient += bool(re.search(r"(body|html|:root)[^{]*\{[^}]*linear-gradient", s))
    types = set(re.findall(r"type\s*[=:]\s*['\"](sine|square|triangle|sawtooth)['\"]", s))
    sine_only += types == {"sine"} and "createBufferSource" not in s
    t = re.search(r"\[style:\s*([^/\]]+?)\s*/\s*sound:\s*([^\]]+?)\s*\]", s[:4000])
    if t:
        tagged += 1; style[t.group(1)] += 1; sound[t.group(2)] += 1
n = len(apps) or 1
print("%d apps since %s" % (len(apps), since))
print("top fonts: %s" % ", ".join("%s %d%%" % (k, 100 * v // n) for k, v in font.most_common(5)))
print("gradient page background: %d%%   sine-only sound: %d%%   tagged: %d%%"
      % (100 * gradient // n, 100 * sine_only // n, 100 * tagged // n))
print("styles: %s" % dict(style.most_common()))
print("sounds: %s" % dict(sound.most_common()))
