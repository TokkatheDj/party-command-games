"""amigo_voice_clips.py - record a game's lines in Amigo's own voice (28 Oct 2026).

Amigo, the desk coqui, talks with the Piper voice and speed set in
C:\\Users\\Lance\\Amigo\\amigo-speech.json (en_US-ryan-high at 0.9). A game on the
Arcade or a claude.ai page can't reach his server, so every line in the game's
LINES table is recorded here, squeezed to a small mp3, and written into the game
as its CLIPS table.

Lines with numbers in them are recorded WHOLE for every number the game can use
("What's 3 plus 2?", "Level 4!"): a separate "3" clip joined on sounded choppy, and
short single words came out clipped. Pieces cut at the numbers ("Level" + "26") are
kept as a back-up for anything outside those ranges; keys_of() must match
clipKeys() in the game.

Run it with the Python that has piper (the one Start Coqui.cmd uses) after
changing LINES:
    python3.13 amigo_voice_clips.py kids_apps/2026-10-27-amigos-candy-math.html
"""
import base64
import io
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

AMIGO = Path(r"C:\Users\Lance\Amigo")
FFMPEG = (r"C:\Users\Lance\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")
POWERS = [2 ** k for k in range(5, 15)]           # tile sizes 32 .. 16384
# back-up single numbers: counts, levels, question numbers and tile sizes
NUMBERS = list(range(0, 31)) + POWERS
# Every value a placeholder can take, by LINES group, so whole lines can be recorded.
# {n} = how many in the chain (the group says how big), {L} = level, {v} = a new biggest tile.
VALUES = {
    "chain5": {"n": range(5, 8)}, "chain8": {"n": range(8, 12)}, "chain12": {"n": range(12, 31)},
    "level": {"L": range(2, 26)}, "top": {"v": POWERS},
}
# "Ko-KEE" in capitals gets spelled out letter by letter; this is how he says it
RESPELL = {"Ko-KEE": "ko-kee"}
# Trim the silence Piper leaves at both ends so lines start straight away - but gently:
# a hard cut ate soft first sounds ("Hi" came out "Oh", "seven" lost its s).
TRIM = ("silenceremove=start_periods=1:start_threshold=-62dB:start_silence=0.08,areverse,"
        "silenceremove=start_periods=1:start_threshold=-62dB:start_silence=0.08,areverse")


def keys_of(text):
    out = []
    for part in re.split(r"(\d+)", text):
        if re.fullmatch(r"\d+", part):
            out.append("#" + part)
        else:
            s = part.strip()
            if re.search(r"[a-z]", s, re.I):
                out.append(s)
    return out


def lines_in(html):
    """(group, line) for every line in the game's LINES table."""
    block = re.search(r"const LINES = \{(.*?)\n\};", html, re.S).group(1)
    out = []
    for group, body in re.findall(r"(\w+):\s*\[(.*?)\]", block, re.S):
        out += [(group, line) for line in re.findall(r'"((?:[^"\\]|\\.)*)"', body)]
    return out


def filled(group, line):
    """The line with every number the game can put in it - or as it is if it has none."""
    if group == "quizAdd":     # must match askCoach(): two numbers adding up to 10 at most
        return [line.replace("{a}", str(a)).replace("{b}", str(b)) for a in range(1, 10) for b in range(1, 11 - a)]
    if group == "quizSub":     # 2..10 take away 1..one less
        return [line.replace("{a}", str(a)).replace("{b}", str(b)) for a in range(2, 11) for b in range(1, a)]
    holes = re.findall(r"\{(\w)\}", line)
    if not holes:
        return [line]
    if len(holes) > 1 or holes[0] not in VALUES.get(group, {}):
        return []              # no known range: the back-up pieces cover it
    return [line.replace("{%s}" % holes[0], str(x)) for x in VALUES[group][holes[0]]]


def phrases_in(html):
    whole, pieces = set(), set()
    for group, line in lines_in(html):
        whole.update(filled(group, line))
        pieces.update(k for k in keys_of(re.sub(r"\{\w\}", "7", line)) if not k.startswith("#"))
    return sorted(whole | pieces)


def main(game):
    path = Path(game)
    html = path.read_text(encoding="utf-8")
    cfg = json.loads((AMIGO / "amigo-speech.json").read_text(encoding="utf-8"))
    voice = PiperVoice.load(str(AMIGO / "voices" / (cfg["voice"] + ".onnx")))
    syn = SynthesisConfig(length_scale=1.0 / float(cfg.get("speed") or 1.0))
    respell = dict(cfg.get("words") or {}, **RESPELL)
    clips = {}
    for key in phrases_in(html) + ["#%d" % n for n in NUMBERS]:
        spoken = key[1:] if key.startswith("#") else key
        for word, said in respell.items():
            spoken = spoken.replace(word, said)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(spoken, w, syn_config=syn)
        mp3 = subprocess.run([FFMPEG, "-v", "error", "-f", "wav", "-i", "pipe:0", "-af", TRIM,
                              "-ac", "1", "-ar", "22050", "-b:a", "32k", "-f", "mp3", "pipe:1"],
                             input=buf.getvalue(), capture_output=True, check=True).stdout
        clips[key] = base64.b64encode(mp3).decode("ascii")
    table = "/*CLIPS*/const CLIPS = " + json.dumps(clips, separators=(",", ":"), ensure_ascii=False) + ";"
    lines = html.split("\n")
    at = [i for i, l in enumerate(lines) if l.startswith("/*CLIPS*/")]
    if len(at) != 1:
        sys.exit("expected one /*CLIPS*/ line in %s, found %d" % (game, len(at)))
    lines[at[0]] = table
    path.write_text("\n".join(lines), encoding="utf-8")
    size = sum(len(v) for v in clips.values())
    print("%d clips (%d lines and pieces, %d back-up numbers), %.0f KB of audio, written into %s"
          % (len(clips), len(clips) - len(NUMBERS), len(NUMBERS), size / 1024, path.name))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "kids_apps/2026-10-27-amigos-candy-math.html")
