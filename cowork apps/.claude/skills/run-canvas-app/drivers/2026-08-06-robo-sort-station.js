// Drives Robo Sort Station: drag an item into its matching chute, try a wrong
// chute, then use the tap-select path. Items carry data-bin = correct chute key.
exports.drive = async (page, box, { shot, wait }) => {

  const centerOf = async sel => page.$eval(sel, el => {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }).catch(() => null);

  // pick the left-most item that is sitting on the belt
  const grabTarget = async () => page.evaluate(() => {
    const items = [...document.querySelectorAll('.item')];
    if (!items.length) return null;
    items.sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
    const el = items[0];
    const r = el.getBoundingClientRect();
    return { bin: el.dataset.bin, x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });

  const hud = async () => page.evaluate(() => ({
    score: document.getElementById('scoreChip').textContent.trim(),
    level: document.getElementById('levelChip').textContent.trim(),
    rule:  document.getElementById('ruleTitle').textContent.trim(),
    items: document.querySelectorAll('.item').length,
    bins:  [...document.querySelectorAll('.bin')].map(b => b.dataset.key)
  }));

  await page.click('#playBtn');
  await wait(900);
  await shot('start');
  console.log('after start:', JSON.stringify(await hud()));

  // ---- 1. DRAG an item into the correct chute ----
  let t = await grabTarget();
  if (!t) { console.log('!! no items on the belt'); return; }
  let bin = await centerOf('.bin[data-key="' + t.bin + '"]');
  console.log('drag: item(' + t.bin + ') -> chute ' + t.bin);

  await page.mouse.move(t.x, t.y);
  await page.mouse.down();
  await page.mouse.move(t.x, t.y - 40, { steps: 5 });
  await page.mouse.move(bin.x, bin.y, { steps: 14 });
  await wait(200);
  await shot('dragging');
  await page.mouse.up();
  await wait(700);
  console.log('after correct drag:', JSON.stringify(await hud()));
  await shot('after-correct-drag');

  // ---- 2. DRAG into a WRONG chute (should bounce back, score unchanged) ----
  t = await grabTarget();
  if (t) {
    const keys = (await hud()).bins;
    const wrongKey = keys.find(k => k !== t.bin);
    bin = await centerOf('.bin[data-key="' + wrongKey + '"]');
    console.log('drag: item(' + t.bin + ') -> WRONG chute ' + wrongKey);
    await page.mouse.move(t.x, t.y);
    await page.mouse.down();
    await page.mouse.move(bin.x, bin.y, { steps: 14 });
    await page.mouse.up();
    await wait(900);
    console.log('after wrong drag:', JSON.stringify(await hud()));
    await shot('after-wrong-drag');
  }

  // ---- 3. TAP-SELECT path: tap the item, then tap the chute ----
  t = await grabTarget();
  if (t) {
    console.log('tap-select: item(' + t.bin + ') then chute ' + t.bin);
    await page.mouse.move(t.x, t.y);
    await page.mouse.down();
    await page.mouse.up();               // zero-movement tap => select
    await wait(500);
    await shot('picked');
    await page.click('.bin[data-key="' + t.bin + '"]');
    await wait(800);
    console.log('after tap-select:', JSON.stringify(await hud()));
    await shot('after-tap-select');
  }

  // ---- 4. finish the level to see the celebration ----
  for (let i = 0; i < 12; i++) {
    const g = await grabTarget();
    if (!g) break;
    const b = await centerOf('.bin[data-key="' + g.bin + '"]');
    if (!b) break;
    await page.mouse.move(g.x, g.y);
    await page.mouse.down();
    await page.mouse.move(b.x, b.y, { steps: 10 });
    await page.mouse.up();
    await wait(500);
    const done = await page.$eval('#winOverlay', el => !el.hidden).catch(() => false);
    if (done) break;
  }
  await wait(1200);
  console.log('end of level:', JSON.stringify(await hud()));
  await shot('level-complete');

  // ---- 5. next level shows a different rule ----
  const winShown = await page.$eval('#winOverlay', el => !el.hidden).catch(() => false);
  if (winShown) {
    await page.click('#nextBtn');
    await wait(900);
    console.log('level 2:', JSON.stringify(await hud()));
    await shot('level-2');
  } else {
    console.log('!! win overlay never appeared');
  }
};
