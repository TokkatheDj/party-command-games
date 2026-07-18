/**
 * App-specific driver for music_apps/2026-06-25-gravity-bells.html.
 * Exercises the three interactive features and captures before/after evidence:
 *   - THEME picker  (aurora)         -> UI + canvas recolor
 *   - SOUND picker  (glass)          -> replaces old scale/key, must not throw
 *   - stuck-marble dissolve          -> 10 resting marbles -> 0 after the ~2.5s window
 *
 * The app binds mousedown to <canvas> and mousemove/mouseup to window, so we drive
 * with real Playwright mouse events at coordinates from the canvas rect.
 */
exports.drive = async (page, box, { shot, wait }) => {
  const px = (f) => box.x + box.w * f;
  const py = (f) => box.y + box.h * f;

  // controls
  await page.selectOption("#themeSel", "aurora");
  await page.selectOption("#soundSel", "glass");

  // draw a flat catch-bar (bar tool is the default)
  await page.mouse.move(px(0.30), py(0.82));
  await page.mouse.down();
  await page.mouse.move(px(0.70), py(0.82), { steps: 8 });
  await page.mouse.up();

  // drop a row of marbles onto it
  await page.click('#toolSeg button[data-tool="drop"]');
  for (let k = 0; k < 10; k++) await page.mouse.click(px(0.34 + (k * 0.32) / 9), py(0.76));
  await page.click('#toolSeg button[data-tool="bar"]');

  await wait(1000);
  await shot("rest"); // marbles resting on the bar

  // let rAF advance past the stuck window (STUCK_DISSOLVE ~2.5s) + fade
  await wait(4500);
  await shot("after"); // confined marbles have dissolved -> empty field
};
