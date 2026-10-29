#!/usr/bin/env node
/**
 * subject_worksheets_check.js - every Science/English/Art/History/Spanish worksheet can be done in
 * student mode, and the checking is right (29 Oct 2026). Adapted from worksheet_blanks_check.js.
 *
 * For every topic, in student mode, at phone (390px) and desktop (1440px) width:
 *  - each tap-through step: only the first is open, exactly one choice is right, no duplicate
 *    choices, and the right choice opens the next step;
 *  - Check on an empty problem says so beside it and records nothing; Check All skips empty ones;
 *  - each stored answer (fill / multiple choice / matching / order / label) is marked right, and a
 *    wrong one - including a wrong answer that CONTAINS the right one - is marked wrong;
 *  - Spanish: an answer typed without accents passes and the accented spelling is shown;
 *  - short answers: the model answer only opens after the student writes something;
 *  - every "blank" spot holds a text box (the old blanks check);
 *  - the score reaches total/total; no NaN or undefined shows; no dialog opens; no console error;
 *  - no sideways scroll, every SVG has a viewBox and stays inside its worksheet.
 * Also: the Answer Key, Print, Reset, Streamlined and Add-your-own-question controls.
 *
 *   node subject_worksheets_check.js [page URL or file] [screenshot dir]
 * Prints JSON; exit 1 on any failure.
 */
const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const PAGE = process.argv[2] || path.join(__dirname, "Educational Apps/educational_apps/2026-10-29-guided-subject-worksheets.html");
const SHOTS = process.argv[3] || "";

function toUrl(p) {
  return /^(https?|file):/.test(p) ? p : "file:///" + path.resolve(p).replace(/\\/g, "/").replace(/ /g, "%20");
}

// Runs inside the page: does every problem of one topic, returns a list of failures.
async function doTopic(modId) {
  const NOT_SPOTS = ["blank-line", "blank-text"];
  const fails = [];
  const F = (k, m) => fails.push(`${k}: ${m}`);
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const res = key => document.getElementById("check-result-" + key.replace(":", "-"));
  const resClass = key => { const r = res(key); return r && r.classList.contains("show") ? (["correct", "incorrect", "pending", "seen"].find(c => r.classList.contains(c)) || "?") : "none"; };
  const fire = (el, type) => el.dispatchEvent(new Event(type, { bubbles: true }));
  const strip = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "");
  const accents = !!TOPIC_BY_ID[modId].accents;

  switchModule(modId);
  await sleep(10);
  const mod = document.getElementById("mod-" + modId);
  if (!mod.classList.contains("active")) F(modId, "module did not open");
  if (!mod.querySelector(".ws-video")) F(modId, "no help video bar");
  if (!mod.querySelector(".ws-tips")) F(modId, "no Key Rules & Tips");

  // Check All on an untouched sheet: nothing is marked
  checkAllProblems();
  if (Object.keys(studentState.results).some(k => k.startsWith(modId + ":"))) F(modId, "Check All marked an empty sheet");

  const probs = PROBS[modId];
  for (let i = 0; i < probs.length; i++) {
    const p = probs[i], key = modId + ":" + i, el = probEl(key);
    if (!el) { F(key, "problem not rendered"); continue; }
    const checkBtn = el.querySelector(".prob-check-bar .check-btn:not(.show-answer)");
    const check = () => { checkBtn.click(); };

    // tap-through steps
    if (p.steps) {
      const steps = el.querySelectorAll(".interactive-step");
      for (let s = 0; s < steps.length; s++) {
        const st = steps[s];
        if (st.classList.contains("locked") || !st.offsetParent) F(key, `step ${s + 1} not open when it should be`);
        if (s + 1 < steps.length && !steps[s + 1].classList.contains("locked")) F(key, `step ${s + 2} open too early`);
        const btns = [...st.querySelectorAll(".choice-btn")];
        const right = btns.filter(b => b.dataset.correct === "true");
        if (right.length !== 1) F(key, `step ${s + 1} has ${right.length} right choices`);
        if (new Set(btns.map(b => b.textContent.trim().toLowerCase())).size !== btns.length) F(key, `step ${s + 1} duplicate choices`);
        const wrong = btns.find(b => b.dataset.correct !== "true");
        if (wrong) { wrong.click(); if (st.classList.contains("i-done")) F(key, `step ${s + 1} a wrong choice finished it`); }
        right[0] && right[0].click();
        if (!st.classList.contains("i-done")) F(key, `step ${s + 1} right choice did not finish it`);
      }
      if (!el.querySelector(".prob-score-badge.i-show")) F(key, "steps badge did not show");
    }

    // empty Check says so, records nothing
    if (checkBtn) {
      check();
      if (resClass(key) !== "pending") F(key, "Check on an empty answer did not say so (" + resClass(key) + ")");
      if (studentState.results[key]) F(key, "empty Check recorded a result");
    }

    if (p.t === "fill") {
      const inputs = [...el.querySelectorAll(".blank input")];
      const blanks = fillBlanks(p);
      if (inputs.length !== blanks.length) F(key, `${inputs.length} boxes for ${blanks.length} blanks`);
      inputs.forEach(inp => { if (!inp.offsetParent) F(key, "a blank's box is hidden"); });
      const typeAll = f => { inputs.forEach((inp, b) => { inp.value = f(blanks[b], b); fire(inp, "input"); }); check(); return resClass(key); };
      if (typeAll(() => "zzqx") !== "incorrect") F(key, "wrong word not marked wrong");
      if (typeAll(a => a[0] + " zz") !== "incorrect") F(key, "answer + extra words was accepted");
      if (typeAll(a => "zz " + a[0]) !== "incorrect") F(key, "extra words + answer was accepted");
      if (p.cs) { // capital-letter questions: the right letters in the wrong case are wrong
        if (blanks.some(a => a[0].toLowerCase() !== a[0]) && typeAll(a => a[0].toLowerCase()) !== "incorrect") F(key, "case-sensitive answer accepted in lower case");
      } else if (typeAll(a => "  " + a[0].toUpperCase() + ". ") !== "correct") F(key, "answer in caps with spaces/period not accepted");
      if (accents && blanks.some(a => strip(a[0]) !== a[0])) {
        if (typeAll(a => strip(a[0])) !== "correct") F(key, "answer without accents not accepted");
        else if (!blanks.filter(a => strip(a[0]) !== a[0]).every(a => res(key).textContent.includes(a[0]))) F(key, "accented spelling not shown");
      }
      blanks.forEach((a, b) => a.forEach(alt => { // every listed alternative passes on its own
        inputs.forEach((inp, bb) => { inp.value = bb === b ? alt : blanks[bb][0]; fire(inp, "input"); });
        check(); if (resClass(key) !== "correct") F(key, `alternative "${alt}" not accepted`);
      }));
    }
    else if (p.t === "mc") {
      const opts = [...el.querySelectorAll(".mc-opt")];
      if (opts.length !== p.opts.length) F(key, "option count");
      if (new Set(opts.map(o => o.textContent.trim().toLowerCase())).size !== opts.length) F(key, "duplicate options");
      if (opts.filter(o => o.dataset.ok === "1").length !== 1) F(key, "not exactly one right option");
      opts.find(o => o.dataset.ok !== "1").click();
      if (resClass(key) !== "incorrect" || studentState.results[key] !== "incorrect") F(key, "wrong option not marked wrong");
      opts[p.ans].click();
      if (resClass(key) !== "correct") F(key, "right option not marked right");
    }
    else if (p.t === "match") {
      const sels = [...el.querySelectorAll(".match-row select")], rights = LAYOUT[key].rights, n = rights.length;
      sels.forEach(s => { if (!s.offsetParent) F(key, "a match box is hidden"); });
      const setAll = f => { sels.forEach((s, r) => { s.value = String(f(rights.indexOf(p.pairs[r][1]))); fire(s, "change"); }); check(); return resClass(key); };
      sels[0].value = String(rights.indexOf(p.pairs[0][1])); fire(sels[0], "change"); check();
      if (resClass(key) !== "pending") F(key, "half-done matching not flagged");
      if (setAll(c => (c + 1) % n) !== "incorrect") F(key, "wrong matches not marked wrong");
      if (setAll(c => c) !== "correct") F(key, "right matches not marked right");
    }
    else if (p.t === "order") {
      const pool = el.querySelector(".ord-pool"), seq = el.querySelector(".ord-seq"), shown = LAYOUT[key].shown;
      if (shown.every((x, j) => x === p.items[j])) F(key, "order starts already solved");
      const tapInOrder = list => list.forEach(it => { pool.querySelector(`.chip[data-si="${shown.indexOf(it)}"]`).click(); });
      const clear = () => [...seq.querySelectorAll(".chip")].forEach(c => c.click());
      tapInOrder(p.items.slice().reverse()); check();
      if (resClass(key) !== "incorrect") F(key, "reversed order not marked wrong");
      clear();
      if (seq.querySelectorAll(".chip").length || pool.querySelectorAll(".chip").length !== p.items.length) F(key, "tap-to-send-back failed");
      tapInOrder(p.items); check();
      if (resClass(key) !== "correct") F(key, "right order not marked right");
    }
    else if (p.t === "label") {
      const names = LAYOUT[key].names, rows = [...el.querySelectorAll(".lbl-row")], spots = [...el.querySelectorAll(".lbl-spot")];
      if (rows.length !== p.parts.length || spots.length !== p.parts.length) F(key, "rows/spots do not match parts");
      if (el.querySelector(".lbl-svg svg").textContent.toLowerCase().split(/\s+/).some(w => p.parts.some(n => n.toLowerCase() === w && n.length > 3))) F(key, "diagram shows a part name");
      const pick = (s, name) => { spots[s].dispatchEvent(new MouseEvent("click", { bubbles: true })); [...el.querySelectorAll(".lbl-names .chip")].find(c => c.textContent === name).click(); };
      p.parts.forEach((n, s) => pick(s, p.parts[(s + 1) % p.parts.length]));
      check();
      if (resClass(key) !== "incorrect") F(key, "wrong labels not marked wrong");
      p.parts.forEach((n, s) => pick(s, n));
      check();
      if (resClass(key) !== "correct") F(key, "right labels not marked right");
      if (names.length !== new Set(names).size) F(key, "duplicate names in word bank");
    }
    else if (p.t === "short") {
      const ta = el.querySelector("textarea"), btn = el.querySelector(".show-answer"), box = el.querySelector(".solution-box");
      btn.click();
      if (box.classList.contains("revealed") || resClass(key) !== "pending") F(key, "model answer opened before writing");
      ta.value = "My answer."; fire(ta, "input"); btn.click();
      if (!box.classList.contains("revealed") || !box.offsetParent) F(key, "model answer did not open after writing");
    }
    if (p.t !== "short" && studentState.results[key] !== "correct") F(key, "result not saved as correct");
  }

  const total = probs.filter(p => p.t !== "short").length;
  if (document.getElementById("pp-score").textContent !== `${total} / ${total}`) F(modId, "score shows " + document.getElementById("pp-score").textContent + ", expected " + total + " / " + total);
  const txt = document.body.innerText;
  if (/\bNaN\b|\bundefined\b|\[object Object\]/.test(txt)) F(modId, "NaN/undefined/[object Object] on page");

  // blanks check (from worksheet_blanks_check.js)
  mod.querySelectorAll(".worksheet .problem [class*=blank]").forEach(b => {
    if (b.closest(".solution-box")) return;
    const c = [...b.classList].find(c => /blank/.test(c) && !NOT_SPOTS.includes(c));
    if (c && !b.querySelector("input, textarea, select")) F(modId, "untypeable ." + c);
  });
  return fails;
}

async function layoutCheck(page, modId) {
  return page.evaluate(id => {
    switchModule(id);
    const out = [], de = document.documentElement, mod = document.getElementById("mod-" + id);
    if (de.scrollWidth > de.clientWidth + 1) out.push(`${id}: sideways scroll (${de.scrollWidth} > ${de.clientWidth})`);
    const ws = mod.querySelector(".worksheet").getBoundingClientRect();
    mod.querySelectorAll("svg").forEach(s => {
      if (!s.getAttribute("viewBox")) out.push(`${id}: svg without viewBox`);
      const r = s.getBoundingClientRect();
      if (r.width && (r.right > ws.right + 1 || r.left < ws.left - 1)) out.push(`${id}: svg wider than its worksheet`);
    });
    mod.querySelectorAll("button, select, input, textarea, a").forEach(b => {
      const r = b.getBoundingClientRect();
      if (r.width && r.right > de.clientWidth + 1) out.push(`${id}: control past the right edge: ${(b.textContent || b.tagName).trim().slice(0, 30)}`);
    });
    return out;
  }, modId);
}

(async () => {
  const browser = await chromium.launch();
  const url = toUrl(PAGE);
  const report = { url, topics: 0, problems: 0, failures: [], dialogs: [], errors: [] };
  for (const width of [390, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: width < 600 ? 844 : 900 } });
    page.on("dialog", d => { report.dialogs.push(`${width}px: ${d.type()} "${d.message()}"`); d.dismiss(); });
    page.on("pageerror", e => report.errors.push(`${width}px: ${e.message}`));
    page.on("console", m => { if (m.type() === "error") report.errors.push(`${width}px console: ${m.text()}`); });
    await page.goto(url, { waitUntil: "load" });
    await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
    await page.reload({ waitUntil: "load" });
    await page.addScriptTag({ content: "window.__prints = 0; window.print = () => { window.__prints++; };" });

    const topics = await page.evaluate(() => Object.keys(SUBJECTS).flatMap(s => SUBJECTS[s].map(t => t.id)));
    const counts = await page.evaluate(() => Object.values(PROBS).reduce((n, a) => n + a.length, 0));
    if (width === 1440) { report.topics = topics.length; report.problems = counts; }

    // nav: every subject, band and topic button opens something
    const navFails = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll("#subject-bar .subj-btn").forEach(b => {
        b.click();
        if (currentSubject !== b.dataset.subj) out.push("subject button " + b.textContent);
        document.querySelectorAll("#subject-subbar .band-btn").forEach(bb => {
          bb.click();
          if (currentBand !== bb.dataset.band) out.push("band button " + bb.textContent);
          document.querySelectorAll("#topic-bar .topic-btn").forEach(tb => {
            tb.click();
            if (currentModule !== tb.dataset.id || !document.querySelector(".module.active")) out.push("topic button " + tb.textContent);
          });
        });
      });
      return out;
    });
    report.failures.push(...navFails.map(f => `${width}px nav: ${f}`));

    // paper mode first: layout + screenshot
    for (const id of topics) report.failures.push(...(await layoutCheck(page, id)).map(f => `${width}px paper: ${f}`));
    await page.evaluate(() => toggleStudentMode());
    for (const id of topics) {
      const f = await page.evaluate(doTopic, id).catch(e => [`${id}: threw ${e.message.split(/\r?\n/)[0]}`]);
      report.failures.push(...f.map(x => `${width}px: ${x}`));
      report.failures.push(...(await layoutCheck(page, id)).map(f => `${width}px student: ${f}`));
    }
    if (SHOTS) {
      fs.mkdirSync(SHOTS, { recursive: true });
      for (const subj of await page.evaluate(() => Object.keys(SUBJECTS))) {
        const first = await page.evaluate(s => { const t = SUBJECTS[s].find(t => PROBS[t.id].some(p => p.t === "label")) || SUBJECTS[s][0]; switchModule(t.id); window.scrollTo(0, 0); return t.id; }, subj);
        await page.screenshot({ path: path.join(SHOTS, `${width}-${first}-student.png`), fullPage: true });
      }
    }

    // controls: answer key, print, streamlined, add-a-question, reset
    const ctl = await page.evaluate(async () => {
      const out = [], id = currentModule, mod = document.getElementById("mod-" + id);
      document.getElementById("ak-toggle-btn").click();
      if (!document.body.classList.contains("answer-key-mode")) out.push("answer key did not turn on");
      if ([...mod.querySelectorAll(".solution-box")].some(b => !b.offsetParent)) out.push("answer key: a solution box is hidden");
      document.getElementById("ak-toggle-btn").click();
      document.querySelector(".gbtns .gprint:last-child").click();
      if (window.__prints !== 1) out.push("print button did not call print()");
      mod.querySelector(".diff-streamlined").click();
      if (mod.querySelector(".steps") && mod.querySelector(".steps").offsetParent) out.push("streamlined still shows steps");
      mod.querySelector(".diff-scaffolded").click();
      // add one of each question type, check it works, remove them
      const f = mod.querySelector(".ed-form"), set = (sel, v) => { f.querySelector(sel).value = v; };
      const add = (type, q, a, list) => { const fm = document.querySelector("#mod-" + id + " .ed-form"); fm.querySelector(".ed-type").value = type; edTypeChanged(fm.querySelector(".ed-type")); fm.querySelector(".ed-q").value = q; fm.querySelector(".ed-a").value = a || ""; fm.querySelector(".ed-list").value = list || ""; fm.querySelector(".act.primary").click(); return document.querySelector("#mod-" + id + " .ed-msg").className; };
      const n0 = PROBS[id].length;
      if (add("fill", "No blank here", "x") !== "ed-msg no") out.push("editor accepted a fill-in with no ___");
      if (add("mc", "Pick <b>one</b>", "right", "wrong 1\nwrong 2") !== "ed-msg ok") out.push("editor: mc not added");
      if (add("fill", "Ends a question: ___", "?") !== "ed-msg no") out.push("editor accepted a punctuation-only answer");
      if (add("fill", "The sky is ___.", "blue\nlight blue") !== "ed-msg ok") out.push("editor: fill not added");
      if (add("match", "Match", "", "a = 1\nb = 2") !== "ed-msg ok") out.push("editor: match not added");
      if (add("order", "Order", "", "first\nsecond\nthird") !== "ed-msg ok") out.push("editor: order not added");
      if (add("short", "Why?", "Because.") !== "ed-msg ok") out.push("editor: short not added");
      if (PROBS[id].length !== n0 + 5) out.push("editor: expected 5 added questions");
      const addedPrompt = probEl(id + ":" + n0).querySelector(".prob-prompt");
      if (addedPrompt.querySelector("b") || addedPrompt.textContent.indexOf("<b>one</b>") === -1) out.push("editor: question text not escaped");
      const k = id + ":" + (n0 + 1), inp = probEl(k).querySelector(".blank input");
      inp.value = "Light Blue"; inp.dispatchEvent(new Event("input", { bubbles: true })); checkProblem(k);
      if (studentState.results[k] !== "correct") out.push("editor: added fill-in did not grade");
      // Show Answer: a wrong answer stays wrong, and the right answer picked after the reveal doesn't score
      const km = id + ":" + n0, opts = probEl(km).querySelectorAll(".mc-opt");
      [...opts].find(o => o.dataset.ok !== "1").click();
      probEl(km).querySelector(".show-answer").click();
      if (studentState.results[km] !== "incorrect") out.push("Show Answer erased a wrong answer");
      [...opts].find(o => o.dataset.ok === "1").click();
      if (studentState.results[km] === "correct") out.push("a right answer after Show Answer still scored");
      for (let j = 0; j < 5; j++) edRemove(id, 0);
      if (PROBS[id].length !== n0) out.push("editor: remove failed");
      // the same editor field keeps an answer that contains a slash
      add("fill", "Half is ___.", "1/2");
      if (JSON.stringify(PROBS[id][n0].a) !== '["1/2"]') out.push("editor split 1/2 into separate answers");
      edRemove(id, 0);
      // accents optional: a missing accent passes, an accent the answer doesn't have fails
      if (!wordsMatch("estas", ["estás"], true).ok) out.push("missing accent not accepted");
      if (wordsMatch("él", ["el"], true).ok) out.push("él accepted for el");
      if (wordsMatch("sí", ["si"], true).ok) out.push("sí accepted for si");
      // printed label problems carry a word bank with every name
      document.querySelectorAll(".problem[data-type=label]").forEach(pr => {
        const p = probByKey(pr.dataset.key), wb = pr.querySelector(".paper .word-bank");
        if (!wb || !p.parts.concat(p.bank || []).every(n => wb.textContent.includes(n))) out.push(pr.dataset.key + ": printed label problem has no full word bank");
      });
      // reset needs two taps, no dialog
      const r = document.getElementById("pp-reset"); r.click();
      if (!Object.keys(studentState.results).length) out.push("reset cleared on the first tap");
      r.click();
      if (Object.keys(studentState.results).length) out.push("reset did not clear");
      if (lastCelebratedModule !== null || document.getElementById("pp-time").textContent !== "0:00") out.push("reset left the confetti flag or the timer");
      return out;
    });
    report.failures.push(...ctl.map(f => `${width}px controls: ${f}`));
    await page.close();
  }
  await browser.close();
  report.ok = !report.failures.length && !report.dialogs.length && !report.errors.length && report.topics > 0;
  console.log(JSON.stringify(report, null, 1));
  process.exit(report.ok ? 0 : 1);
})();
