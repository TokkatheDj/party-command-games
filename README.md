# Party Command Games

**Play now: https://tokkathedj.github.io/party-command-games/**

A single-file party games web app — no install, no server, no framework. Open in any browser and play.

## Games

### 🔥 Floor is Lava
A random timer triggers a lava strike. Everyone must get off the floor before time runs out. Configurable min/max wait time and lava duration. Includes a creepy warning voice ~5 seconds before the lava hits.

### 👆 Simon Says
Simon gives commands — some legit, some tricks. Players tap **I Did It!** or **Got Tricked** to score. Includes body movement, silly, and multi-step commands. Three speed settings.

### 🚦 Red / Green Light
Green light means go, red light means freeze. Players who move on red are out. Includes **Sudden Death** mode where green phases are under 1 second.

### 🥔 Hot Potato
A beeping potato with escalating speed — whoever holds it when it explodes is eliminated. Tracks elimination count across rounds.

### 🪑 Musical Chairs
Simulated music plays while players walk around chairs. When the music stops, someone is out. Tracks players and chairs automatically, round by round.

## Features

- **Auto / Manual mode** on Hot Potato and Musical Chairs — hosts can let the game trigger events randomly, or press a button to control exactly when the potato explodes or the music stops
- **Cartoony voices** for safe/happy moments; **scary deep voices** for danger moments (uses Web Speech API)
- **Escalating beeps** and **chiptune melody** via Web Audio API — no audio files needed
- **Sound mute toggle** in the top corner
- **Animated splash screen** on each game entry
- Fully responsive — works on phones, tablets, and desktop

## Usage

Just open `party-games.html` in a browser. No build step, no dependencies, no internet required after the first load.

For best results on mobile, add to your home screen so it runs full-screen.
