/* pad.js - play the Amigo Arcade with a game controller (Xbox, PlayStation, Switch Pro...), 18 Nov 2026.
 *
 * Uses the browser's standard Gamepad API, so the same file works on Windows, Mac, Chromebooks,
 * Android and iPad (pair the controller over Bluetooth, then press any button on it).
 *
 *   left stick / D-pad  arrow keys            A        Space, or press what's under the pointer
 *   right stick         moves a pointer       hold A   drag (link candies)
 *   B                   Escape                Start    Enter
 *
 * <script src="pad.js" data-mode="...">
 *   menu   the Arcade front page: the D-pad moves between games, A opens one
 *   game   a game page: buttons become the keys above, plus the pointer
 *   relay  play.html: the student game runs in a locked frame, so presses are passed in to
 *          the small receiver that play.html adds to the game (window.AmigoPad.receiver)
 * A game that reads the controller itself (Squad Leader) is left alone: the moment it gets a
 * controller from navigator.getGamepads, this file stops sending anything, so no press counts twice.
 */
(() => {
  if (window.AmigoPad) return;
  const me = document.currentScript;
  const MODE = (me && me.dataset.mode) || "game";
  const realGet = navigator.getGamepads ? navigator.getGamepads.bind(navigator) : null;
  let gameHasOwnPad = false, frameHasOwnPad = false;

  // a game that asks for controllers and gets one handles them itself: stand aside
  if (realGet && MODE !== "menu") {
    try {
      navigator.getGamepads = function () {
        const list = realGet();
        if (!polling && [...list].some(p => p && p.connected)) gameHasOwnPad = true;
        return list;
      };
    } catch (e) { /* read-only in some browsers: then nothing to detect */ }
  }

  const KEYS = {
    ArrowUp: ["ArrowUp", 38], ArrowDown: ["ArrowDown", 40], ArrowLeft: ["ArrowLeft", 37], ArrowRight: ["ArrowRight", 39],
    " ": ["Space", 32], Enter: ["Enter", 13], Escape: ["Escape", 27],
  };

  /* ---------- sending ---------- */
  const stage = () => (MODE === "relay" ? document.querySelector("#stage iframe") : null);

  function keyEvent(type, key) {
    const [code, keyCode] = KEYS[key];
    if (MODE === "relay") { const f = stage(); if (f) f.contentWindow.postMessage({ amigoPad: "key", type, key }, "*"); return null; }
    const ev = fireKey(document, type, key, code, keyCode);
    if (type === "keydown" && key.startsWith("Arrow") && ev && !ev.defaultPrevented) navFocus(document, key);
    // A the game ignored on a menu (19 Nov 2026: Boo Tag's "1 Player / 2 Players" menu): highlight
    // the likeliest button so A visibly does something; the next A presses it
    if (type === "keydown" && key === " " && ev && !ev.defaultPrevented) navFocus(document, "first");
    return ev;
  }

  function pointerAt(type, x, y) {
    if (MODE === "relay") {
      const f = stage(); if (!f) return;
      const r = f.getBoundingClientRect();
      if (x < r.left || x > r.right || y < r.top || y > r.bottom) return;
      f.contentWindow.postMessage({ amigoPad: "ptr", type, x: x - r.left, y: y - r.top }, "*");
      return;
    }
    firePointer(document, type, x, y);
  }

  /* ---------- the pointer (right stick) ---------- */
  let cur = null, cx = innerWidth / 2, cy = innerHeight / 2, curShown = false, held = false;
  function cursorEl() {
    if (cur && cur.isConnected) return cur;
    cur = document.createElement("div");
    cur.setAttribute("aria-hidden", "true");
    cur.style.cssText = "position:fixed;left:0;top:0;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;" +
      "border:4px solid #ffe14d;box-shadow:0 0 0 3px #141a33,0 0 12px #ffe14d;pointer-events:none;z-index:2147483647;display:none";
    (document.body || document.documentElement).appendChild(cur);
    return cur;
  }
  function showCursor(on) {
    curShown = on; const c = cursorEl();
    c.style.display = on ? "block" : "none";
    c.style.transform = `translate(${cx}px,${cy}px) scale(${held ? 0.8 : 1})`;
  }

  /* ---------- the front page: move between games ---------- */
  function focusables() {
    return [...document.querySelectorAll("a[href],button:not([disabled]),[tabindex]:not([tabindex='-1'])")]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width && r.height && getComputedStyle(e).visibility !== "hidden"; });
  }
  function moveFocus(dir) {
    const all = focusables(); if (!all.length) return;
    const now = document.activeElement && all.includes(document.activeElement) ? document.activeElement : null;
    if (!now) { focus(all.find(e => e.classList.contains("card")) || all[0]); return; }
    const a = now.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
    let best = null, bestD = Infinity;
    for (const e of all) {
      if (e === now) continue;
      const b = e.getBoundingClientRect(), dx = b.left + b.width / 2 - ax, dy = b.top + b.height / 2 - ay;
      const along = { ArrowRight: dx, ArrowLeft: -dx, ArrowDown: dy, ArrowUp: -dy }[dir];
      const across = dir === "ArrowLeft" || dir === "ArrowRight" ? Math.abs(dy) : Math.abs(dx);
      if (along <= 2) continue;
      const d = along + across * 2;
      if (d < bestD) { bestD = d; best = e; }
    }
    if (best) focus(best);
  }
  function focus(e) {
    e.focus({ preventScroll: true });
    e.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  if (MODE === "menu") {
    const st = document.createElement("style");
    st.textContent = "a:focus-visible,button:focus-visible,.card:focus{outline:5px solid #ffe14d;outline-offset:4px;box-shadow:0 0 0 9px #141a33}";
    document.head.appendChild(st);
  }
  // Safari won't move focus to a link unless it has a tabindex
  function tabbable() { if (MODE === "menu") for (const a of document.querySelectorAll("a[href]:not([tabindex])")) a.tabIndex = 0; }

  /* ---------- a short hint the first time a controller shows up ---------- */
  let hinted = false;
  function hint() {
    if (hinted) return; hinted = true;
    const h = document.createElement("div");
    h.setAttribute("role", "status");
    h.textContent = MODE === "menu"
      ? "🎮 Controller ready! Move with the stick or D-pad, press A to play."
      : "🎮 Controller ready! Stick = move, A = jump / press, right stick = pointer.";
    h.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);max-width:calc(100% - 32px);" +
      "background:#141a33;color:#fff;font:700 16px system-ui,sans-serif;padding:10px 16px;border-radius:12px;" +
      "border:3px solid #ffe14d;z-index:2147483646;pointer-events:none;transition:opacity .6s";
    (document.body || document.documentElement).appendChild(h);
    setTimeout(() => { h.style.opacity = "0"; }, 3500);
    setTimeout(() => h.remove(), 4300);
  }

  /* ---------- reading the controller, every frame ---------- */
  let polling = false, padIdx = -1;
  const was = {};                         // logical control -> pressed last frame
  const repeatAt = {};                    // menu auto-repeat
  function readPad() {
    if (!realGet) return null;
    let list = [];
    polling = true;
    try { list = [...realGet()].filter(p => p && p.connected && p.buttons && p.buttons.length); } catch (e) { list = []; }
    polling = false;
    if (!list.length) return null;
    const live = list.find(p => p.buttons.some(b => b.pressed));   // Windows can list a phantom pad first
    if (live) padIdx = live.index;
    return list.find(p => p.index === padIdx) || list[0];
  }
  // Button LAYOUT (19 Nov 2026): the browser numbers buttons by their LABEL, so on a Nintendo-style
  // pad (Switch Pro, Joy-Con, many 8BitDo) the bottom button, printed "B", arrives as B. Games should
  // follow POSITION, like an Xbox: bottom = confirm (A), right = back (B), left = X, top = Y. For such a
  // pad, swap A<->B and X<->Y. "Auto" goes by the pad's name; the Controller Practice page can set it by
  // hand for a site (localStorage "amigoPadLayout" = "nintendo" | "xbox").
  const NINTENDO = /nintendo|pro controller|switch|joy-?con|057e/i;
  // NOT an Apple exception: on Lance's iPad (19 Nov, Chrome and Safari) the bottom button also arrives as B
  // by LABEL, like Windows. An earlier guess that iPads report by position was wrong.
  function nintendoLayout(p) {
    let o = null;
    try { o = localStorage.getItem("amigoPadLayout"); } catch (e) {}
    if (o === "nintendo") return true;
    if (o === "xbox") return false;
    return NINTENDO.test((p && p.id) || "");
  }
  const POS = [1, 0, 3, 2];
  let swap = false;
  const btn = (p, i) => { const j = swap && i < 4 ? POS[i] : i; return !!(p.buttons[j] && (p.buttons[j].pressed || p.buttons[j].value > 0.5)); };

  function edge(name, down, onDown, onUp) {
    if (down && !was[name]) onDown && onDown();
    if (!down && was[name]) onUp && onUp();
    was[name] = down;
  }

  function frame(t) {
    requestAnimationFrame(frame);
    const p = readPad();
    if (!p) return;
    swap = nintendoLayout(p);
    hint();
    if (gameHasOwnPad || frameHasOwnPad) return;          // the game drives itself
    const ax = p.axes[0] || 0, ay = p.axes[1] || 0, rx = p.axes[2] || 0, ry = p.axes[3] || 0;
    const dir = {
      ArrowLeft: btn(p, 14) || ax < (was.ArrowLeft ? -0.35 : -0.5),
      ArrowRight: btn(p, 15) || ax > (was.ArrowRight ? 0.35 : 0.5),
      ArrowUp: btn(p, 12) || ay < (was.ArrowUp ? -0.35 : -0.5),
      ArrowDown: btn(p, 13) || ay > (was.ArrowDown ? 0.35 : 0.5),
    };
    const anyDir = Object.values(dir).some(Boolean);

    if (MODE === "menu") {
      // the Games Arcade plays games in a frame over its menu: while one is open the menu stays
      // still (the game's own pad.js has the controller) and View / Select goes back to the games
      if (api.paused && api.paused()) { edge("Back", btn(p, 8), () => api.onBack && api.onBack()); return; }
      tabbable();
      for (const k of Object.keys(dir)) {
        if (dir[k] && (!was[k] || t >= repeatAt[k])) { moveFocus(k); repeatAt[k] = t + (was[k] ? 140 : 380); }
        was[k] = dir[k];
      }
      edge("A", btn(p, 0) || btn(p, 9), () => { const a = document.activeElement; if (a && a !== document.body) a.click(); else moveFocus("ArrowDown"); });
      return;
    }

    for (const k of Object.keys(dir)) edge(k, dir[k], () => keyEvent("keydown", k), () => keyEvent("keyup", k));
    if (anyDir && curShown && !held) showCursor(false);

    // right stick moves the pointer (speed grows with the push)
    const m = Math.hypot(rx, ry);
    if (m > 0.2) {
      const sp = 14 * Math.min(1, (m - 0.2) / 0.8) ** 1.6;
      cx = Math.max(0, Math.min(innerWidth - 1, cx + (rx / m) * sp * 1.6));
      cy = Math.max(0, Math.min(innerHeight - 1, cy + (ry / m) * sp * 1.6));
      showCursor(true);
      if (held) pointerAt("pointermove", cx, cy);
    }

    edge("A", btn(p, 0), () => {
      if (curShown) { held = true; showCursor(true); pointerAt("pointerdown", cx, cy); return; }
      const a = document.activeElement;
      if (MODE !== "relay" && a && /^(BUTTON|A|SUMMARY)$/.test(a.tagName)) { a.click(); return; }
      if (pressStart()) { was.Aclick = true; return; }
      const ev = keyEvent("keydown", " ");
      if (ev && !ev.defaultPrevented && !document.querySelector(".amigo-pad-focus")) {
        const hit = document.elementFromPoint(innerWidth / 2, innerHeight / 2);
        if (hit && hit.tagName === "CANVAS") { cx = innerWidth / 2; cy = innerHeight / 2; showCursor(true); }
      }
    }, () => {
      if (held) { held = false; showCursor(true); pointerAt("pointerup", cx, cy); return; }
      if (was.Aclick) { was.Aclick = false; return; }
      keyEvent("keyup", " ");
    });
    edge("B", btn(p, 1), () => keyEvent("keydown", "Escape"), () => keyEvent("keyup", "Escape"));
    edge("Start", btn(p, 9), () => { if (pressStart()) was.Sclick = true; else keyEvent("keydown", "Enter"); },
      () => { if (was.Sclick) was.Sclick = false; else keyEvent("keyup", "Enter"); });
  }

  // A title screen with only a START button and nothing focused (Click Click): A or Start presses it
  // Most wanted first (19 Nov 2026: Line Limit's A pressed the small "New game" in its header
  // instead of the big "Start the game"): a Start / Play button beats Spin / Roll / Deal
  const START = [/^\W*(start(?!\s*(over|again))|play(?!\s*again)|begin|let'?s (go|play|start)|tap to (start|play)|1 player|one player|single player|solo)/i,
                 /^\W*(go\b|ready|spin|roll|deal|new word|let'?s)/i];   // never "New game" / "Start over" / "Play again": they would restart a game in progress (Line Limit, ABC Barnyard)
  function pressStart() {
    if (MODE === "relay") return false;            // inside the locked frame the game decides
    const a = document.activeElement;
    if (a && a !== document.body && a !== document.documentElement) return false;
    const shown = [...document.querySelectorAll("button,[role=button],input[type=button],input[type=submit]")].filter(e => {
      const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
      return r.width && r.height && cs.visibility !== "hidden" && !e.disabled && r.bottom > 0 && r.top < innerHeight;
    });
    const label = e => (e.innerText || e.value || e.getAttribute("aria-label") || "").trim();
    let b = null;
    for (const re of START) { b = shown.find(e => re.test(label(e))); if (b) break; }
    if (!b) return false;
    b.click();
    return true;
  }

  /* ---------- turning controls into page events (also used inside the locked frame) ---------- */
  function fireKey(doc, type, key, code, keyCode) {
    const ev = new KeyboardEvent(type, { key, code, bubbles: true, cancelable: true, composed: true });
    for (const [k, v] of [["keyCode", keyCode], ["which", keyCode], ["charCode", 0]]) {
      try { Object.defineProperty(ev, k, { get: () => v }); } catch (e) {}
    }
    // like a real keyboard: from the focused element, else <body> (never document: Blocky Obby calls e.target.closest)
    const target = doc.activeElement || doc.body || doc;
    target.dispatchEvent(ev);
    return ev;
  }
  // D-pad in menus (19 Nov 2026: Candy Math's and Brick Dash's menus ignored the D-pad). When the game didn't
  // use an arrow key and the middle of the screen isn't a game canvas (so a menu or title screen is showing),
  // move a highlighted selection to the nearest button that way; A then presses it. Self-contained, because
  // the receiver inside a student game's locked frame runs the same function.
  function navFocus(doc, dir) {
    var W = doc.defaultView, hit = doc.elementFromPoint(W.innerWidth / 2, W.innerHeight / 2);
    if (hit && hit.tagName === "CANVAS") return;
    if (!doc.getElementById("amigo-pad-focus-style")) {
      var st = doc.createElement("style"); st.id = "amigo-pad-focus-style";
      st.textContent = ".amigo-pad-focus{outline:4px solid #ffcc33 !important;outline-offset:3px !important;box-shadow:0 0 0 8px rgba(20,26,51,.55) !important}";
      (doc.head || doc.documentElement).appendChild(st);
    }
    var all = [].slice.call(doc.querySelectorAll("button,a[href],[role=button],input[type=button],input[type=submit],select")).filter(function (e) {
      var r = e.getBoundingClientRect(), cs = W.getComputedStyle(e);
      return r.width > 4 && r.height > 4 && !e.disabled && cs.visibility !== "hidden" && cs.display !== "none" && r.bottom > 0 && r.top < W.innerHeight && r.right > 0 && r.left < W.innerWidth
        && doc.elementFromPoint(Math.min(W.innerWidth - 1, Math.max(0, r.left + r.width / 2)), Math.min(W.innerHeight - 1, Math.max(0, r.top + r.height / 2))) !== null;
    });
    if (!all.length) return;
    var now = all.indexOf(doc.activeElement) >= 0 ? doc.activeElement : null, best = null;
    if (!now) {
      // first press: a Start / Play button if there is one, else the button nearest the middle of the screen
      var lbl = function (e) { return (e.innerText || e.value || e.getAttribute("aria-label") || "").trim(); };
      best = all.filter(function (e) { return /^\W*(start(?!\s*(over|again))|play(?!\s*again)|begin|go\b|let'?s|ready|1 player|one player|single player|solo|spin|roll|deal|new word)/i.test(lbl(e)); })[0] || all.slice().sort(function (x, y) {
        var rx = x.getBoundingClientRect(), ry = y.getBoundingClientRect(), cx = W.innerWidth / 2, cy = W.innerHeight / 2;
        return Math.hypot(rx.left + rx.width / 2 - cx, rx.top + rx.height / 2 - cy) - Math.hypot(ry.left + ry.width / 2 - cx, ry.top + ry.height / 2 - cy);
      })[0];
    }
    else {
      var a = now.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2, bestD = Infinity;
      all.forEach(function (e) {
        if (e === now) return;
        var b = e.getBoundingClientRect(), dx = b.left + b.width / 2 - ax, dy = b.top + b.height / 2 - ay;
        var along = { ArrowRight: dx, ArrowLeft: -dx, ArrowDown: dy, ArrowUp: -dy }[dir];
        var across = dir === "ArrowLeft" || dir === "ArrowRight" ? Math.abs(dy) : Math.abs(dx);
        if (along <= 2) return;
        var d = along + across * 2;
        if (d < bestD) { bestD = d; best = e; }
      });
    }
    if (!best) best = now;   // nowhere further that way: keep (and show) the current one
    if (!best) return;
    var old = doc.querySelector(".amigo-pad-focus"); if (old) old.classList.remove("amigo-pad-focus");
    best.classList.add("amigo-pad-focus");
    try { best.focus({ preventScroll: true }); } catch (e) { best.focus(); }
  }
  function firePointer(doc, type, x, y) {
    const el = doc.elementFromPoint(x, y); if (!el) return;
    const base = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, screenX: x, screenY: y, view: doc.defaultView };
    const down = type !== "pointerup";
    const pe = { ...base, pointerId: 1, pointerType: "mouse", isPrimary: true, button: 0, buttons: down ? 1 : 0, width: 1, height: 1, pressure: down ? 0.5 : 0 };
    el.dispatchEvent(new PointerEvent(type, pe));
    const mouse = { pointerdown: "mousedown", pointermove: "mousemove", pointerup: "mouseup" }[type];
    el.dispatchEvent(new MouseEvent(mouse, { ...base, button: 0, buttons: down ? 1 : 0 }));
    if (type === "pointerup") {
      el.dispatchEvent(new MouseEvent("click", { ...base, button: 0, buttons: 0 }));
      if (el.focus && /^(BUTTON|A|INPUT|SELECT|TEXTAREA)$/.test(el.tagName)) el.focus();
    }
  }

  // the receiver play.html appends to each student game (it runs inside the locked frame)
  const receiver = `<script>(function(){
  if (window.__amigoPadIn) return; window.__amigoPadIn = 1;
  var C = ${JSON.stringify(KEYS)};
  var fireKey = ${fireKey.toString()}, firePointer = ${firePointer.toString()}, navFocus = ${navFocus.toString()};
  var real = navigator.getGamepads ? navigator.getGamepads.bind(navigator) : null, told = false;
  if (real) try { navigator.getGamepads = function () { var l = real();
    for (var i = 0; i < l.length; i++) if (l[i] && l[i].connected && !told) { told = true; parent.postMessage({ amigoPad: "own" }, "*"); }
    return l; }; } catch (e) {}
  addEventListener("message", function (e) {
    if (e.source !== parent || !e.data || !e.data.amigoPad) return;
    var d = e.data;
    if (d.amigoPad === "key" && C[d.key]) {
      var ev = fireKey(document, d.type === "keyup" ? "keyup" : "keydown", d.key, C[d.key][0], C[d.key][1]);
      if (d.type === "keydown" && ev && !ev.defaultPrevented) {
        if (/^Arrow/.test(d.key)) navFocus(document, d.key);
        else if ((d.key === " " || d.key === "Enter") && document.activeElement && /^(BUTTON|A|SUMMARY)$/.test(document.activeElement.tagName)) document.activeElement.click();
        else if (d.key === " ") navFocus(document, "first");
      }
    }
    else if (d.amigoPad === "ptr" && /^pointer(down|move|up)$/.test(d.type)) firePointer(document, d.type, +d.x, +d.y);
  });
})();<\/script>`;

  if (MODE === "relay") {
    addEventListener("message", e => {
      const f = stage();
      if (f && e.source === f.contentWindow && e.data && e.data.amigoPad === "own") frameHasOwnPad = true;   // just a yes/no
    });
  }

  const api = window.AmigoPad = {
    receiver,
    newGame() { frameHasOwnPad = false; held = false; },   // play.html calls this on Restart
    nintendoLayout,                                        // the practice page draws buttons by the same rule
    paused: null,                                          // menu pages: () => true while a game is open
    onBack: null,                                          // ...and what View / Select does then
  };
  requestAnimationFrame(frame);
})();
