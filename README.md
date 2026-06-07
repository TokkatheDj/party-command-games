# Party Command Games

**Play now: https://tokkathedj.github.io/party-command-games/**

<img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://tokkathedj.github.io/party-command-games/" alt="QR code" />

A single-file party games web app — no install, no server, no framework. Open in any browser and play.

## Games

### 🔥 Floor is Lava
A random timer triggers a lava strike. Everyone must get off the floor before time runs out. Configurable min/max wait time and lava duration. Includes a creepy warning voice ~5 seconds before the lava hits.

### 👆 Simon Says
Simon gives commands — some legit, some tricks. Players tap **I Did It!** or **Got Tricked** to score. Includes body movement, silly, and multi-step commands. Three speed settings.

### 🚦 Red / Green Light
Green light means go, red light means freeze. Players who move on red are out. Includes **Sudden Death** mode where green phases are under 1 second.

### 🥔 Hot Potato
A beeping potato with escalating speed — whoever holds it when it explodes is eliminated. After each explosion a **Who's Out?** overlay shows all remaining players so the host can tap who was holding it. Tracks elimination count across rounds.

### 🪑 Musical Chairs
Simulated music plays while players walk around chairs. When the music stops, a 5-second scramble countdown starts, then the **Who's Out?** picker appears. Tracks players and chairs automatically, round by round, down to the last winner.

## Features

- **👥 Player names** — add everyone's names before the game; eliminations show the player's name on screen and remove them from future rounds
- **🏆 Scoreboard** — tracks wins across all games; ranked leaderboard (🥇🥈🥉) updates live after each game, with a win toast announcement and a Reset Wins button
- **Auto / Manual mode** on Hot Potato and Musical Chairs — hosts can let events fire randomly, or control exactly when the potato explodes or the music stops
- **☠️ Eliminate Player button** on Floor is Lava (during lava) and Red/Green Light (during red light) so the host can tag who got caught
- **📲 Share button** on the menu — tap to show a QR code anyone can scan to open the game
- **Cartoony voices** for safe/happy moments; **scary deep voices** for danger moments (Web Speech API)
- **Escalating beeps** and **chiptune melody** via Web Audio API — no audio files needed
- **Sound mute toggle** in the top corner
- **Animated splash screen** on each game entry
- Fully responsive — works on phones, tablets, and desktop

## Usage

Open the link or scan the QR code. No install, no build step, no dependencies.

For best results on mobile, add to your home screen so it runs full-screen.
