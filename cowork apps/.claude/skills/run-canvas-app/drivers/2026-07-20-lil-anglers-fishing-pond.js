exports.drive = async (page, box, { shot, wait }) => {
  const px = f => box.x + box.w * f, py = f => box.y + box.h * f;
  // Start screen -> tap Play
  await page.click('#playBtn');
  await wait(700);
  await shot('start');
  // Drag the hook slowly across the pond at a few depths to scoop fish
  const sweeps = [0.35, 0.55, 0.72];
  for (const depth of sweeps) {
    await page.mouse.move(px(0.12), py(depth));
    await page.mouse.down();
    for (let i = 0; i <= 10; i++) {
      await page.mouse.move(px(0.12 + 0.76 * (i / 10)), py(depth + Math.sin(i) * 0.05), { steps: 3 });
      await wait(120);
    }
    await page.mouse.up();
    await wait(300);
  }
  await shot('after-fishing');
  // let a moment pass for banners/confetti/HUD to settle
  await wait(800);
  await shot('settled');
  // read HUD values from the page for a sanity check
  const bucket = await page.$eval('#bucketNum', el => el.textContent).catch(() => '?');
  const gold = await page.$eval('#goldNum', el => el.textContent).catch(() => '?');
  console.log('HUD bucket=' + bucket + ' gold=' + gold);
};
