import re, pathlib
import pathlib as _pl
# Paths are derived from this file's location so the folder can be moved or the
# repo cloned elsewhere. dashboard/ -> _scheduler/ -> cowork apps/
HERE = _pl.Path(__file__).resolve().parent
COWORK = HERE.parent.parent

p = HERE / "app-factory-floor.html"
html = p.read_text(encoding="utf-8")
css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)

# Every literal color must live in a :root-ish token block, never in a component rule.
bad = []
for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
    sel, body = m.group(1).strip().splitlines()[-1].strip(), m.group(2)
    if sel.startswith(":root") or sel.startswith("@"):
        continue
    for c in re.finditer(r"(?<![-\w])(#[0-9A-Fa-f]{3,8})\b", body):
        bad.append((sel, c.group(1)))

print("literal colors in component rules:", bad if bad else "none")

# A token defined ONLY inside a media/[data-theme] block never applies to the
# un-stamped default document -- the classic unreadable-artifact bug.
root_block = re.search(r":root\{(.*?)\}", css, re.S).group(1)
base = set(re.findall(r"(--[\w-]+)\s*:", root_block))
allvars = set(re.findall(r"(--[\w-]+)\s*:", css))
missing = sorted(v for v in allvars - base)
print("tokens missing from bare :root:", missing if missing else "none")

used = set(re.findall(r"var\((--[\w-]+)", css)) | set(re.findall(r"var\((--[\w-]+)", html))
undef = sorted(v for v in used - allvars if not v.startswith("--cat-")
               and v not in {"--pc", "--cc", "--sc"})
print("var() referencing undefined tokens:", undef if undef else "none")

for need in ("prefers-reduced-motion", "focus-visible", "overflow-x:auto",
             "fonts.googleapis.com", "<title>"):
    print(f"  {'ok ' if need in html else 'MISSING'} {need}")
print("body sets explicit background:", "background:var(--bg)" in css)
