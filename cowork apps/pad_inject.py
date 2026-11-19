"""pad_inject.py - game controllers in every AppVerse app (18 Nov 2026).

serve_apps.py runs every .html app it serves through inject(): one tag, <script src="/pad.js">,
goes in just before the page's last </body>. pad.js (also used by the Amigo Arcade and the Games
Arcade) turns an Xbox / PlayStation / Switch controller into the keys and clicks a game already
understands, and stands aside for a game that reads controllers itself (Squad Leader). With no
controller connected it does nothing.

The app files on disk are never changed.
"""

TAG = b'<script src="/pad.js" data-mode="game"></script>'


def inject(html: bytes) -> bytes:
    """The page with the pad.js tag added, or unchanged if it already loads pad.js."""
    if b"pad.js" in html:                      # the Games Arcade page loads its own (menu) copy
        return html
    low = html.lower()
    at = low.rfind(b"</body>")
    if at < 0:
        return html + TAG
    # a "</body>" inside a script's text (a loader building a page) is not the real one:
    # putting the tag there would break that script, so add it at the very end instead
    if low.rfind(b"<script", 0, at) > low.rfind(b"</script>", 0, at):
        return html + TAG
    return html[:at] + TAG + html[at:]
