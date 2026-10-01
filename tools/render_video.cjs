#!/usr/bin/env node
/*
 * 把 presentation/index.html 逐格錄成 MP4（1280×720），並混入旁白音軌。
 *
 * 需求：Node 18+、playwright（npm i -D playwright 或全域安裝）、ffmpeg
 * 用法：
 *   node tools/render_video.cjs                       # 輸出 video/系統與網路安全.mp4
 *   node tools/render_video.cjs --fps 15 --from 0 --to 60 --out preview.mp4
 *   node tools/render_video.cjs --shots 5,40,120      # 只截圖指定秒數到 build/shots/
 */
const path = require('path');
const fs = require('fs');
const { spawn, execFileSync } = require('child_process');
const crypto = require('crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => {
  if (v.startsWith('--')) a.push([v.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
  return a;
}, []));
const FPS = +(args.fps || 20);

(async () => {
  const launch = { args: ['--force-color-profile=srgb'] };
  if (process.env.HTTPS_PROXY) launch.proxy = { server: process.env.HTTPS_PROXY };
  if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(launch);
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  // Google Fonts 透過 curl 下載並快取（某些代理環境下 Chromium 不信任代理憑證）
  const fontDir = path.join(ROOT, 'build', 'fonts');
  fs.mkdirSync(fontDir, { recursive: true });
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, async route => {
    const u = route.request().url();
    const f = path.join(fontDir, crypto.createHash('sha1').update(u).digest('hex'));
    try {
      if (!fs.existsSync(f)) execFileSync('curl', ['-sSfL', '-A', route.request().headers()['user-agent'] || 'Mozilla/5.0', '-o', f, u]);
      const css = u.includes('googleapis');
      await route.fulfill({ status: 200, body: fs.readFileSync(f), headers: { 'content-type': css ? 'text/css' : 'font/woff2', 'access-control-allow-origin': '*' } });
    } catch (e) { await route.abort(); }
  });
  const url = 'file://' + path.join(ROOT, 'presentation', 'index.html') + '?render';
  await page.goto(url, { waitUntil: 'networkidle' });

  // 先讓所有文字出現一次，確保網路字型的所有子集都已下載
  await page.evaluate(async () => {
    const pre = document.createElement('div');
    pre.style.cssText = 'position:absolute;left:0;top:0;opacity:0.01;font-family:var(--f-display);font-weight:700';
    pre.textContent = window.LESSON.scenes.flatMap(s => s.lines.map(l => l.t)).join('') + document.getElementById('stage').innerText;
    const pre2 = pre.cloneNode(true); pre2.style.fontWeight = '900';
    const pre3 = pre.cloneNode(true); pre3.style.fontFamily = 'var(--f-body)';
    document.body.append(pre, pre2, pre3);
    document.querySelectorAll('.scene').forEach(s => { s.style.display = 'block'; });
    await document.fonts.ready;
    await new Promise(r => setTimeout(r, 1500));
    await document.fonts.ready;
    pre.remove(); pre2.remove(); pre3.remove();
    document.querySelectorAll('.scene').forEach(s => { s.style.display = 'none'; });
  });
  const duration = await page.evaluate(() => window.LESSON_DURATION);

  if (args.shots) {
    const dir = path.join(ROOT, 'build', 'shots');
    fs.mkdirSync(dir, { recursive: true });
    for (const s of String(args.shots).split(',')) {
      const t = +s;
      await page.evaluate(t => { window.renderAt(t - 1); window.renderAt(t); }, t);
      await page.screenshot({ path: path.join(dir, `t${String(t).padStart(5, '0')}.png`) });
    }
    await browser.close();
    console.log('shots →', dir);
    return;
  }

  const from = +(args.from || 0), to = Math.min(+(args.to || duration), duration);
  const out = path.resolve(ROOT, args.out || path.join('video', '系統與網路安全.mp4'));
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const audio = path.join(ROOT, 'presentation', 'audio', 'narration.mp3');
  const ff = spawn('ffmpeg', ['-v', 'error', '-y',
    '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-ss', String(from), '-t', String(to - from), '-i', audio,
    '-c:v', 'libx264', '-preset', 'medium', '-crf', String(args.crf || 27), '-pix_fmt', 'yuv420p', '-tune', 'animation',
    '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', '-shortest', out], { stdio: ['pipe', 'inherit', 'inherit'] });

  const total = Math.ceil((to - from) * FPS);
  const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    const t = from + f / FPS;
    await page.evaluate(t => window.renderAt(t), t);
    const buf = await page.screenshot({ type: 'jpeg', quality: 90 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % (FPS * 30) === 0) console.log(`frame ${f}/${total} (${(t).toFixed(0)}s) ${((Date.now() - t0) / 1000).toFixed(0)}s elapsed`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log('video →', out);
})().catch(e => { console.error(e); process.exit(1); });
