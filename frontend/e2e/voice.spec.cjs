// Voice conversation through the real storefront UI (run with AVC_E2E_SPEECH=1; needs whisper.cpp and the macOS voices).
// The microphone is SUBSTITUTED: getUserMedia returns a stream playing a macOS-voice recording (Vani ta / Rishi en /
// Lekha hi). Everything after that is the product: recorder, silence detection, /speech/transcribe (local whisper.cpp),
// /chat, spoken reply. This is NOT a physical-microphone test.
const { test } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const h = require('./support/helpers.cjs');

const { expect } = h;
test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

const VOICE = { ta: 'Vani', en: 'Rishi', hi: 'Lekha' };
const TURNS = {
  'store-a': [['ta', 'வணக்கம், எனக்கு ஒரு நல்ல hiking bag வேண்டும்.'], ['en', 'Show me the best one under 5000 rupees.'],
    ['ta', 'இதில் எந்த நிறங்கள் கிடைக்கும்?'], ['hi', 'मुझे इसकी कीमत बताइए।']],
  'store-b': [['en', 'I would like some coffee beans.'], ['ta', 'திருப்பி அனுப்பும் கொள்கை என்ன?'],
    ['hi', 'आपकी वापसी नीति क्या है?'], ['en', 'How much is shipping?']],
};
const SCRIPT = { ta: /[஀-௿]/, hi: /[ऀ-ॿ]/, en: /^[^஀-௿ऀ-ॿ]*$/ };

function wav(dir, name, lang, text) {
  const aiff = path.join(dir, `${name}.aiff`); const out = path.join(dir, `${name}.wav`);
  execFileSync('say', ['-v', VOICE[lang], '-o', aiff, text]);
  execFileSync('afconvert', ['-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', aiff, out]);
  return fs.readFileSync(out);
}

// Each getUserMedia call plays the next queued clip (then silence, so the recorder's end-of-speech detection runs).
async function substituteMicrophone(page) {
  await page.addInitScript(() => {
    window.__voiceQueue = [];
    navigator.mediaDevices.getUserMedia = async () => {
      const url = window.__voiceQueue.shift();
      if (!url) throw Object.assign(new Error('no clip'), { name: 'NotFoundError' });
      const ctx = new AudioContext();
      const buf = await ctx.decodeAudioData(await (await fetch(url)).arrayBuffer());
      const src = ctx.createBufferSource(); src.buffer = buf;
      const dest = ctx.createMediaStreamDestination();
      src.connect(dest); src.start(ctx.currentTime + 0.3);
      return dest.stream;
    };
  });
}

test('spoken conversation in the chat: language follows each utterance, interruption and speaking again work', async ({ page }, info) => {
  test.skip(process.env.AVC_E2E_SPEECH !== '1', 'voice run only (AVC_E2E_SPEECH=1)');
  test.setTimeout(180_000);
  const store = info.project.name;
  const s = h.STORES[store];
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'avc-voice-'));
  const clips = TURNS[store].map(([lang, text], i) => ({ lang, text, body: wav(dir, `t${i}`, lang, text) }));
  await page.route('**/__voice/*.wav', (route) => route.fulfill({ status: 200, contentType: 'audio/wav',
    body: clips[Number(route.request().url().match(/(\d+)\.wav$/)[1])].body }));
  await substituteMicrophone(page);
  await page.goto('/');
  await page.getByRole('button', { name: `Open chat with ${s.assistant}` }).click();
  const chat = page.getByRole('dialog', { name: s.assistant });
  await expect(chat).toHaveAttribute('lang', 'ta-IN');                                   // new conversation: Tamil
  await expect(chat.locator('.lang-note')).toContainText('தமிழ், English, हिन्दी');      // automatic language detection on
  const results = [];
  for (let i = 0; i < clips.length; i += 1) {
    const { lang } = clips[i];
    await page.evaluate((n) => window.__voiceQueue.push(`/__voice/${n}.wav`), i);
    const assistantCount = await chat.locator('.bubble-assistant').count();
    const t0 = Date.now();
    await chat.locator('button.mic').click();
    await expect(chat.locator('button.mic')).toHaveAttribute('aria-pressed', 'true');    // listening indicator
    await expect(chat.locator('.bubble-assistant')).toHaveCount(assistantCount + 1, { timeout: 45_000 });
    const reply = chat.locator('.bubble-assistant').last();
    const replyLang = await reply.getAttribute('data-language');
    const clarified = await reply.locator('.lang-choice').count() > 0;
    const heard = (await chat.locator('.bubble-user').last().innerText()).replace(/\s+/g, ' ').slice(0, 60);
    results.push({ expected: lang, heard, replyLang, clarified, seconds: (Date.now() - t0) / 1000 });
    expect(clarified || replyLang === lang, JSON.stringify(results.at(-1))).toBe(true);     // never a wrong language
    if (!clarified) expect(SCRIPT[lang].test((await reply.locator('p').first().innerText()).replace(/“[^”]*”/g, ''))).toBe(true);
    if (clarified) {   // the customer taps their language; the same audio is transcribed in it
      await reply.locator('.lang-choice').getByRole('button', { name: { ta: 'தமிழ்', en: 'English', hi: 'हिन्दी' }[lang] }).click();
      await expect(chat.locator('.bubble-assistant').last()).toHaveAttribute('data-language', lang, { timeout: 45_000 });
    }
    await expect(chat).toHaveAttribute('lang', { ta: 'ta-IN', en: 'en-IN', hi: 'hi-IN' }[lang]);   // conversation follows
  }
  // Interrupt: while a reply is being spoken, pressing the mic stops it and starts listening again.
  const speaking = chat.locator('.chat-speaking');
  const spoke = await speaking.waitFor({ timeout: 8000 }).then(() => true, () => false);
  if (spoke) {
    await page.evaluate(() => window.__voiceQueue.push('/__voice/0.wav'));
    await chat.locator('button.mic').click();
    await expect(speaking).toBeHidden();
    await expect(chat.locator('button.mic')).toHaveAttribute('aria-pressed', 'true');
    await expect(chat.locator('.bubble-assistant').last()).toHaveAttribute('data-language', clips[0].lang, { timeout: 45_000 });
  }
  await info.attach('voice-results.json', { body: JSON.stringify({ results, interruptionTested: spoke }, null, 2), contentType: 'application/json' });
  console.log(`[${store}] voice turns:`, JSON.stringify(results), 'interruption tested:', spoke);
  expect(results.filter((r) => r.replyLang === r.expected).length).toBeGreaterThanOrEqual(3);
});
