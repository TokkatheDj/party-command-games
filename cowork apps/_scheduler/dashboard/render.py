"""Render App Factory Floor: inject real data + a computed OKLCH category scale."""
import json, math, pathlib
import pathlib as _pl
# Paths are derived from this file's location so the folder can be moved or the
# repo cloned elsewhere. dashboard/ -> _scheduler/ -> cowork apps/
HERE = _pl.Path(__file__).resolve().parent
COWORK = HERE.parent.parent

TMP = HERE
data = json.loads((TMP / "factory.json").read_text(encoding="utf-8"))


def oklch_to_hex(L, C, H):
    """OKLCH -> sRGB hex, gamut-clamped. Avoids depending on browser oklch() support."""
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(u):
        u = max(0.0, min(1.0, u))
        u = 1.055 * (u ** (1 / 2.4)) - 0.055 if u > 0.0031308 else 12.92 * u
        return round(max(0.0, min(1.0, u)) * 255)

    return "#{:02X}{:02X}{:02X}".format(enc(r), enc(g), enc(bl))


# One hue per category (25 real + 1 quarantine). Golden-angle spacing so neighbouring
# rows in a sorted list never land on near-identical hues.
NCAT = len(data["categories"]) + 1
GOLDEN = 137.507
hues = [(28 + i * GOLDEN) % 360 for i in range(NCAT)]

light = "\n".join(f"  --cat-{i}:{oklch_to_hex(0.585, 0.132, h)};" for i, h in enumerate(hues))
dark = "\n".join(f"    --cat-{i}:{oklch_to_hex(0.715, 0.112, h)};" for i, h in enumerate(hues))

html = (TMP / "template.html").read_text(encoding="utf-8")

# Emit pure ASCII so the page cannot depend on the host guessing a charset -- served
# without one, em dashes were rendering as mojibake. HTML regions get entities,
# the script region gets \u escapes.
html = html.replace("─", "-")           # box-drawing rules in CSS comments
cut = html.index("<script>")
head, tail = html[:cut], html[cut:]
for ch, ent in (("—", "&mdash;"), ("·", "&middot;"),
                ("●", "&#9679;"), ("◆", "&#9670;"), ("◇", "&#9671;")):
    head = head.replace(ch, ent)
tail = "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in tail)
html = head + tail

html = (html
        .replace("__CATVARS_LIGHT__", light)
        .replace("__CATVARS_DARK__", dark)
        .replace("__NCAT__", str(NCAT))
        .replace("__DATA__", json.dumps(data, separators=(",", ":"))))

out = TMP / "app-factory-floor.html"
out.write_text(html, encoding="utf-8")

print(f"wrote {out}  ({len(html):,} bytes)")
print(f"categories: {len(data['categories'])} + 1 quarantine = {NCAT} hues")
assert "__" not in html.replace("__", "", 0) or True
for token in ("__DATA__", "__CATVARS_LIGHT__", "__CATVARS_DARK__", "__NCAT__"):
    assert token not in html, f"placeholder left unreplaced: {token}"
print("all placeholders substituted")
