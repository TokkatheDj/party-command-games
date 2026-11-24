# Amigo Arcade games

Game files for https://amigo-arcade.vercel.app that are too big to paste into a deploy.
The Arcade's games/<name>.html is a small loader that fetches the file from here
(GitHub Pages sends Access-Control-Allow-Origin: *). Same games, same public audience.

- squad-leader.html - Squad Leader, by Massey M. (from the desktop AppVerse,
  Shooting Games/2026-10-17-space-shooter-squad-leader.html, updated 4 Nov 2026)
- squad-leader-frontier.html - Squad Leader: Frontier, by Massey M. (from the desktop AppVerse,
  Shooting Games/2026-11-02-squad-leader-frontier-rpg.html, updated 6 Nov 2026: two-player co-pilot; P2 from a second device works only
  inside AppVerse at home, through its relay, so here the button stays hidden)
- jungle-jumpers.html - Jungle Jumpers: Monkey Mango Dash (Amigo App Builder, 24 Nov 2026). Changes: after a fall the
  monkey comes back on the last platform it stood on, clear of spikes; the green snakes walk back and forth and can be stomped.
- robo-beat-galaxy.html - Robo-Beat Galaxy, a robot-band beat maker (Amigo App Builder, 24 Nov 2026), unchanged.
- deep-sea-dive-quiz.html - Deep Sea Dive Quiz, 10 ocean questions (Amigo App Builder, 24 Nov 2026). Blue whale fact
  corrected to about 30 m (2.5 school buses).
- covers/ - Arcade cover art for the three games above: gameplay screenshots with Adobe contrast +15, vibrance +25, 480px WebP.
- adobe-test/ - four test games made with Adobe Stock art and Adobe Fonts (23 Nov 2026), not on the
  Arcade home page yet. The Arcade's test/<name>.html loaders fetch them from here.
  - reef-rescue.html - Basic (Amigo Build rules): catch game; Adobe Stock 478346529 vectorized to SVG
  - comet-courier.html - Advanced (Amigo Build rules): gravity flying; Adobe Stock 541053342, background removed
  - marble-maze-3d.html - 3D (three.js from jsDelivr): Adobe Stock 320483183 board texture, Adobe font Yerk
  - star-catcher-vr.html - VR (A-Frame from jsDelivr): Adobe Stock 919344524 360 sky, Adobe font Strelka
  - img/ - the two Stock images, as WebP. The Adobe font kit only allows amigo-arcade.vercel.app.
