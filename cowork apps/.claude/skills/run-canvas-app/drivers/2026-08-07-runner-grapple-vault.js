// TELEMETRY PASS: hold/release swings while sampling window.__gv() every 100ms
// to find out why the player stalls and falls.
exports.drive = async (page, box, { shot, wait }) => {
  const cx = box.x + box.w * 0.5, cy = box.y + box.h * 0.62;
  const gv = () => page.evaluate(() => window.__gv());

  const log = [];
  let t = 0;
  const sample = async (tag) => {
    const s = await gv();
    log.push(String(t).padStart(5) + 'ms ' + tag.padEnd(4) +
      ' y=' + s.y + ' vx=' + s.vx + ' vy=' + s.vy +
      ' hook=' + (s.hooked ? 'Y@' + s.ay : 'n') +
      ' rope=' + s.rope + ' cand=' + (s.cand ? 'Y' : 'n') +
      ' held=' + (s.held ? 'Y' : 'n') + ' ' + s.mode +
      ' wallGap=' + s.wallGap);
    return s;
  };

  await sample('init');
  for (let cyc = 0; cyc < 8; cyc++) {
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    for (let i = 0; i < 7; i++) { await wait(100); t += 100; await sample('HOLD'); }
    await page.mouse.up();
    for (let i = 0; i < 3; i++) { await wait(100); t += 100; await sample('free'); }
    const s = await gv();
    if (s.mode === 'dead') { log.push('---- DIED at ' + t + 'ms, cycle ' + cyc); break; }
  }
  console.log(log.join('\n'));
  console.log('void line is y=' + (await gv()).voidY);
  await shot('telemetry');
};
