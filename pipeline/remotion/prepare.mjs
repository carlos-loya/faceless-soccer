// Per-scene visual resolver. Reads the spec's per-scene visual plan + the generated VO,
// sources a background for EACH scene (KB player photo / Pexels stock), downloads them,
// and writes props.json for the render. This is what makes images progress with the VO.
//
// Usage: node prepare.mjs out/assets/<stem>
//
// STORYBOARD mode (TTV_STORYBOARD=1, arg = a spec path/stem): resolve + download every scene's
// visual EXACTLY as the render will, but WITHOUT any VO (durations come from the spec's planned
// `duration_seconds`). Writes storyboard-props.json (never the render's props.json), so the
// owner can preview which image/background each scene gets before paying for a slow render.
// This is what `pipeline/storyboard.sh` + `storyboard.mjs` use.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../");
const STORYBOARD = !!process.env.TTV_STORYBOARD;

let assetsProps, stem, spec;
if (STORYBOARD) {
  // No VO yet — synthesize the per-scene shells straight from the spec.
  const specArg = process.argv[2] || "out/specs/lamine-yamal-trajectory.json";
  const specPath = specArg.endsWith(".json")
    ? path.resolve(repoRoot, specArg)
    : path.resolve(repoRoot, "out/specs", `${specArg}.json`);
  spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
  stem = path.basename(specPath, ".json");
  assetsProps = {
    spec_stem: stem, topic: spec.topic, comment_bait: spec.comment_bait, cta: spec.cta,
    outro: null,
    scenes: spec.scenes.map((sc) => ({
      on_screen_text: sc.on_screen_text || "",
      stat_callout: sc.stat_callout || "",
      audio: null,                                   // no VO in a storyboard
      audio_seconds: sc.duration_seconds || 3,       // planned duration is the best estimate
      words: null,
    })),
  };
} else {
  const assetsArg = process.argv[2] || "out/assets/lamine-yamal-trajectory";
  const assetsDir = path.resolve(repoRoot, assetsArg);
  assetsProps = JSON.parse(fs.readFileSync(path.join(assetsDir, "props.json"), "utf8"));
  stem = assetsProps.spec_stem;
  spec = JSON.parse(fs.readFileSync(path.join(repoRoot, "out/specs", `${stem}.json`), "utf8"));
}
const pub = path.join(__dirname, "public", stem);
fs.mkdirSync(pub, { recursive: true });

// Vision picks from the pick-images skill (if it ran): scene index -> chosen file (or null).
const candDir = path.join(repoRoot, "out/candidates", stem);
const readJson = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const choices = readJson(path.join(candDir, "choices.json"));
const candManifest = readJson(path.join(candDir, "candidates.json"));

// PEXELS_API_KEY from .env
const envText = fs.existsSync(path.join(repoRoot, ".env"))
  ? fs.readFileSync(path.join(repoRoot, ".env"), "utf8") : "";
const PEXELS = (envText.match(/^\s*PEXELS_API_KEY\s*=\s*(.*)$/m)?.[1] || "").trim().replace(/['"]/g, "");

// Strip emoji from any text BURNED INTO the video (headless Chrome has no emoji font -> boxes).
// Emoji stays in the post captions, never in rendered text.
const stripEmoji = (s) => (s || "")
  .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{1F1E6}-\u{1F1FF}]/gu, "")
  .replace(/\s+/g, " ").trim();

// Reject HTML/error pages saved with an image extension (would silently break the render).
const isImage = (b) =>
  (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) ||                 // JPEG
  (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) || // PNG
  (b[0] === 0x47 && b[1] === 0x49 && b[2] === 0x46) ||                 // GIF
  (b.slice(0, 4).toString("ascii") === "RIFF" && b.slice(8, 12).toString("ascii") === "WEBP");

const cache = new Map(); // url -> local filename (dedupe downloads)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Descriptive UA + 429/error backoff — Wikimedia throttles rapid bursts (returns HTML error pages).
const DL_UA = "TikiTakaFootyTV/1.0 (faceless-soccer content tool; contact: exafterdev@gmail.com)";
async function download(url, name) {
  if (cache.has(url)) return cache.get(url);
  // Owner-provided LOCAL asset (e.g. assets/source/<slug>.jpg) — copy from disk, don't fetch.
  if (!/^https?:\/\//i.test(url)) {
    const src = path.isAbsolute(url) ? url : path.join(repoRoot, url);
    const buf = fs.readFileSync(src);
    if (buf.length < 12 || !isImage(buf)) throw new Error(`not an image: ${src}`);
    const out = name.replace(/\.[^.]+$/, path.extname(src) || ".jpg");
    fs.writeFileSync(path.join(pub, out), buf);
    cache.set(url, `${stem}/${out}`);
    return `${stem}/${out}`;
  }
  let lastErr;
  for (let k = 0; k < 4; k++) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": DL_UA } });
      if (res.status === 429) { await sleep(1500 * (k + 1)); continue; }
      const buf = Buffer.from(await res.arrayBuffer());
      if (buf.length < 12 || !isImage(buf)) {
        lastErr = new Error(`not an image (content-type ${res.headers.get("content-type") || "?"})`);
        await sleep(1200 * (k + 1)); continue;
      }
      fs.writeFileSync(path.join(pub, name), buf);
      cache.set(url, `${stem}/${name}`);
      await sleep(350); // be gentle between downloads
      return `${stem}/${name}`;
    } catch (e) { lastErr = e; await sleep(1000 * (k + 1)); }
  }
  throw lastErr || new Error(`download failed: ${url}`);
}

async function entityPhoto(slug, i) {
  // Works for ANY KB entity: player, stadium, nation — the specific-subject source.
  const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${slug}.json`), "utf8"));
  if (!ent.image?.url) return null;
  const ext = (ent.image.url.split(".").pop() || "jpg").split("?")[0].slice(0, 4);
  const bg = await download(ent.image.url, `s${i}-entity.${ext}`);
  return { bg, credit: ent.image.attribution };
}

// Per-scene corner sticker from a KB entity image (e.g. a nation flag on a reveal beat).
async function entitySticker(slug, i) {
  try {
    const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${slug}.json`), "utf8"));
    // Prefer a background-removed CUTOUT (a player) -> iPhone-sticker style; else the entity image as a flag chip (a nation).
    const cut = path.join(repoRoot, "out/cutouts", `${slug}.png`);
    if (fs.existsSync(cut)) {
      const name = `s${i}-stickercut.png`;
      fs.copyFileSync(cut, path.join(pub, name));
      return { img: `${stem}/${name}`, name: ent.name, cutout: true };
    }
    if (!ent.image?.url) return null;
    const ext = (ent.image.url.split(".").pop() || "png").split("?")[0].slice(0, 4);
    const img = await download(ent.image.url, `s${i}-flag.${ext}`);
    return { img, name: ent.name, flag: true };
  } catch (e) {
    console.log(`  scene ${i}: sticker '${slug}' failed — ${String(e).split("\n")[0].slice(0, 50)}`);
    return null;
  }
}

// For a comparison_split scene ("A vs B"), resolve each side label -> KB entity flag image,
// so the VS clash shows the two flags. Graceful: any side that doesn't resolve -> null.
function vsSideLabels(text) {
  const parts = String(text || "").split(/\s+vs\.?\s+|\s*\|\s*/i);
  if (parts.length !== 2) return null;
  return parts.map((p) => p.trim().replace(/[\s:]*\d{1,4}\s*$/, "").trim());
}
// Label -> KB slug, stripping diacritics so accented surnames match ASCII slugs
// (e.g. "QUIÑONES" -> "quinones", "JIMÉNEZ" -> "jimenez").
function labelToSlug(label) {
  return label.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}
// For a scorers_split, prefer a background-removed CUTOUT (out/cutouts/<slug>.png) per side,
// so the two scorers render as iPhone-sticker cutouts (not boxed photo chips). Null -> silhouette.
function scorerCutouts(text, i) {
  const sides = vsSideLabels(text);
  if (!sides) return null;
  return sides.map((label, k) => {
    const cut = path.join(repoRoot, "out/cutouts", `${labelToSlug(label)}.png`);
    if (fs.existsSync(cut)) {
      const name = `s${i}-cut${k}.png`;
      fs.copyFileSync(cut, path.join(pub, name));
      return `${stem}/${name}`;
    }
    return null;
  });
}
async function vsFlags(text, i) {
  const sides = vsSideLabels(text);
  if (!sides) return null;
  const out = [];
  for (let k = 0; k < 2; k++) {
    const slug = labelToSlug(sides[k]);
    try {
      const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${slug}.json`), "utf8"));
      if (ent.image?.url) {
        const ext = (ent.image.url.split(".").pop() || "png").split("?")[0].slice(0, 4);
        out.push(await download(ent.image.url, `s${i}-vs${k}.${ext}`));
      } else out.push(null);
    } catch { out.push(null); }
  }
  console.log(`  scene ${i}: vs flags ${out.map((f) => (f ? "✓" : "—")).join(" ")}`);
  return out;
}

async function stock(query, i) {
  if (!PEXELS) { console.log(`  scene ${i}: no PEXELS_API_KEY — skipping stock`); return null; }
  const u = `https://api.pexels.com/v1/search?query=${encodeURIComponent(query)}&per_page=1&orientation=portrait`;
  const j = await (await fetch(u, { headers: { Authorization: PEXELS } })).json();
  const p = j.photos?.[0];
  if (!p) { console.log(`  scene ${i}: no Pexels result for "${query}"`); return null; }
  const src = p.src?.portrait || p.src?.large2x || p.src?.original;
  const bg = await download(src, `s${i}-stock.jpg`);
  return { bg, credit: `Photo: ${p.photographer} / Pexels` };
}

// Stock VIDEO b-roll — MOVING generic atmosphere (crowd, stadium, confetti) from Pexels Videos.
// Generic only (never a specific player). Pexels' video endpoint needs a browser-like UA.
const PEXELS_UA = "Mozilla/5.0 (X11; Linux x86_64) TikiTakaFootyTV/1.0";
async function downloadVideo(url, name) {
  if (cache.has(url)) return cache.get(url);
  const res = await fetch(url, { headers: { "User-Agent": PEXELS_UA } });
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length < 1000) throw new Error(`video too small (${buf.length}b)`);
  fs.writeFileSync(path.join(pub, name), buf);
  cache.set(url, `${stem}/${name}`);
  await sleep(350);
  return `${stem}/${name}`;
}
async function stockVideo(query, i) {
  // 1) Curated, vision-vetted b-roll library (reliable) — match visual_query to a category slug.
  const slug = String(query || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const curated = path.resolve(repoRoot, "assets/broll", `${slug}.mp4`);
  if (slug && fs.existsSync(curated)) {
    const name = `s${i}-broll.mp4`;
    fs.copyFileSync(curated, path.join(pub, name));
    // Curated b-roll is our own AI-generated (Veo) atmosphere — no attribution required, so no credit.
    console.log(`  scene ${i}: stock_video (curated: ${slug})`);
    return { bgVideo: `${stem}/${name}`, credit: null };
  }
  // 2) Fallback: live Pexels search (a lottery — last resort for an uncurated query).
  if (!PEXELS) { console.log(`  scene ${i}: no PEXELS_API_KEY — skipping stock_video`); return null; }
  const u = `https://api.pexels.com/videos/search?query=${encodeURIComponent(query)}&per_page=5&orientation=portrait`;
  const j = await (await fetch(u, { headers: { Authorization: PEXELS, "User-Agent": PEXELS_UA } })).json();
  for (const v of (j.videos || [])) {
    // portrait mp4, height closest to 1280 (HD without being huge)
    const files = (v.video_files || []).filter((f) => /mp4/.test(f.file_type || "") && (f.height || 0) >= (f.width || 0));
    if (!files.length) continue;
    files.sort((a, b) => Math.abs((a.height || 0) - 1920) - Math.abs((b.height || 0) - 1920));
    try {
      const bgVideo = await downloadVideo(files[0].link, `s${i}-stockvid.mp4`);
      return { bgVideo, credit: `Video: ${v.user?.name || "Pexels"} / Pexels` };
    } catch (e) { /* try the next candidate */ }
  }
  console.log(`  scene ${i}: no portrait mp4 for "${query}"`);
  return null;
}

// Wikimedia Commons image search — finds a FREE photo of a SPECIFIC real thing (a stadium,
// the World Cup trophy, an event) that generic stock won't have.
async function commons(query, i) {
  const u = `https://commons.wikimedia.org/w/api.php?action=query&generator=search` +
    `&gsrsearch=${encodeURIComponent(query)}&gsrnamespace=6&gsrlimit=12` +
    `&prop=imageinfo&iiprop=url|extmetadata|mime|size&format=json`;
  const j = await (await fetch(u, { headers: { "User-Agent": "TikiTakaFootyTV/1.0" } })).json();
  const pages = Object.values(j.query?.pages || {}).sort((a, b) => (a.index || 0) - (b.index || 0));
  for (const p of pages) {
    const ii = p.imageinfo?.[0];
    if (!ii || !/jpeg|png/.test(ii.mime || "")) continue;
    if ((ii.width || 0) < 600) continue;
    const lic = (ii.extmetadata?.LicenseShortName?.value || "").toLowerCase();
    if (!/cc|public domain|cc0|pdm/.test(lic)) continue;
    const artist = (ii.extmetadata?.Artist?.value || "").replace(/<[^>]+>/g, "").trim();
    const ext = (ii.url.split(".").pop() || "jpg").split("?")[0].slice(0, 4);
    const bg = await download(ii.url, `s${i}-commons.${ext}`);
    return { bg, credit: `${artist || "Wikimedia"} / ${ii.extmetadata?.LicenseShortName?.value || "CC"} via Wikimedia Commons` };
  }
  console.log(`  scene ${i}: no free Commons image for "${query}"`);
  return null;
}

// Resolve a nation/club slug -> { flag image, 3-letter code, name } for the scoreboard + group table.
async function nationFlag(slug, i, tag) {
  const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${slug}.json`), "utf8"));
  if (!ent.image?.url) throw new Error(`${slug} has no image`);
  const ext = (ent.image.url.split(".").pop() || "png").split("?")[0].slice(0, 4);
  const img = await download(ent.image.url, `${tag}-${i}.${ext}`);
  const aliasCode = (ent.aliases || []).find((x) => /^[A-Za-z]{2,3}$/.test(x));
  const code = (ent.code || aliasCode || (ent.name || slug).slice(0, 3)).toUpperCase();
  return { img, name: ent.name || slug, code };
}

const scenes = [];
for (let i = 0; i < assetsProps.scenes.length; i++) {
  const a = assetsProps.scenes[i];
  const v = spec.scenes[i] || {};
  let base = null;
  if (a.audio) {
    base = path.basename(a.audio);
    fs.copyFileSync(path.resolve(repoRoot, a.audio), path.join(pub, base));
  }

  let visual = null;
  const ckey = String(i + 1);
  const hasChoice = choices && ckey in choices;
  if (hasChoice) {
    // Vision pick wins: a chosen file is used; an explicit null -> brand graphic (no bg).
    const chosen = choices[ckey];
    if (chosen) {
      try {
        const ext = (chosen.split(".").pop() || "jpg").slice(0, 4);
        fs.copyFileSync(path.resolve(repoRoot, chosen), path.join(pub, `s${i + 1}-pick.${ext}`));
        const cred = candManifest?.[ckey]?.candidates?.find((c) => c.file === chosen)?.credit;
        visual = { bg: `${stem}/s${i + 1}-pick.${ext}`, credit: cred };
        console.log(`  scene ${i + 1}: vision-picked ✓`);
      } catch (e) {
        console.log(`  scene ${i + 1}: pick failed — ${String(e).split("\n")[0].slice(0, 60)}`);
      }
    } else {
      console.log(`  scene ${i + 1}: vision-picked none → brand graphic`);
    }
  } else {
    try {
      if (v.visual_source === "entity") visual = await entityPhoto(v.visual_query, i + 1);
      else if (v.visual_source === "commons") visual = await commons(v.visual_query, i + 1);
      else if (v.visual_source === "stock") visual = await stock(v.visual_query, i + 1);
      else if (v.visual_source === "stock_video") visual = await stockVideo(v.visual_query, i + 1);
      // "ai" -> later (needs billing); "graphic" -> no background
    } catch (e) {
      console.log(`  scene ${i + 1}: visual failed — ${String(e).split("\n")[0].slice(0, 60)}`);
    }
    console.log(`  scene ${i + 1}: ${v.visual_source || "graphic"}${visual ? " ✓" : ""}`);
  }

  let scSticker = null;
  if (v.sticker_entity) scSticker = await entitySticker(v.sticker_entity, i + 1);

  let vsImages = null;
  if (v.graphic_type === "comparison_split" || v.graphic_type === "scorers_split")
    vsImages = await vsFlags(a.on_screen_text, i + 1);
  let vsCutouts = null;
  if (v.graphic_type === "scorers_split") {
    vsCutouts = scorerCutouts(a.on_screen_text, i + 1);
    console.log(`  scene ${i + 1}: scorer cutouts ${(vsCutouts || []).map((c) => (c ? "✓" : "—")).join(" ")}`);
  }

  // Group-standings table for this beat: resolve each row's nation flag + code. The renderer
  // shows a ranked table (flag + code + points) and HIDES the running scoreboard on this scene.
  let groupTable = null;
  if (Array.isArray(v.group_table) && v.group_table.length) {
    groupTable = [];
    for (let r = 0; r < v.group_table.length; r++) {
      const row = v.group_table[r];
      try {
        const f = await nationFlag(row.team, i + 1, `gt${r}`);
        groupTable.push({
          code: f.code, flag: f.img, name: f.name,
          points: row.points, played: row.played, gd: row.gd,
          highlight: row.highlight === true,
        });
      } catch (e) { console.log(`  scene ${i + 1}: group row ${row.team} failed — ${String(e).split("\n")[0].slice(0, 50)}`); }
    }
    console.log(`  scene ${i + 1}: group table ${groupTable.length} rows`);
  }

  scenes.push({
    on_screen_text: stripEmoji(a.on_screen_text),
    stat_callout: stripEmoji(a.stat_callout || ""),
    graphic_type: v.graphic_type || "",
    ...(base ? { audioFile: `${stem}/${base}` } : {}),
    seconds: a.audio_seconds || 3,
    // Storyboard preview needs the PLAN (what was asked) next to the RESULT (what resolved).
    ...(STORYBOARD ? {
      visual_source: v.visual_source || "graphic",
      visual_query: v.visual_query || "",
      voiceover: v.voiceover || "",
    } : {}),
    bg: visual?.bg,
    ...(visual?.bgVideo ? { bgVideo: visual.bgVideo } : {}),
    credit: visual?.credit,
    ...(scSticker ? { sticker: scSticker } : {}),
    ...(vsImages ? { vsImages } : {}),
    ...(vsCutouts ? { vsCutouts } : {}),
    ...(a.words?.length ? { words: a.words } : {}),
    ...(v.camera ? { camera: v.camera } : {}),
    ...(v.score ? { score: v.score } : {}),
    ...(groupTable ? { group_table: groupTable } : {}),
    ...(v.subscribe_chip ? { subscribe_chip: true } : {}),
  });
}

// Subject sticker: the main entity's photo, pinned in the corner across the whole video.
let sticker;
if (spec.subject) {
  try {
    const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${spec.subject}.json`), "utf8"));
    const cutoutPath = path.join(repoRoot, "out/cutouts", `${spec.subject}.png`);
    if (fs.existsSync(cutoutPath)) {
      fs.copyFileSync(cutoutPath, path.join(pub, "sticker.png"));
      sticker = { img: `${stem}/sticker.png`, name: ent.name, cutout: true };
      console.log(`sticker: ${ent.name} (cutout)`);
    } else if (ent.image?.url) {
      const ext = (ent.image.url.split(".").pop() || "jpg").split("?")[0].slice(0, 4);
      sticker = { img: await download(ent.image.url, `sticker.${ext}`), name: ent.name, cutout: false };
      console.log(`sticker: ${ent.name} (circular fallback — run pipeline/cutout.py ${spec.subject} for a cutout)`);
    }
  } catch (e) { console.log(`sticker failed: ${String(e).split("\n")[0].slice(0, 60)}`); }
}

// Outro VO (the spoken comment-bait question), played over the end card.
let outro;
if (assetsProps.outro?.audio) {
  const ob = path.basename(assetsProps.outro.audio);
  fs.copyFileSync(path.resolve(repoRoot, assetsProps.outro.audio), path.join(pub, ob));
  outro = { audioFile: `${stem}/${ob}`, seconds: assetsProps.outro.seconds };
}

// Atmosphere background behind the comment-bait end card (curated b-roll; generic only).
let endCard;
try {
  const eb = await stockVideo("gold-confetti", 99);
  if (eb?.bgVideo) endCard = { bgVideo: eb.bgVideo, credit: eb.credit };
} catch (e) { console.log(`end-card bg failed: ${String(e).split("\n")[0].slice(0, 50)}`); }

// Persistent head-to-head badge (top-left, under the watermark) for match videos:
// resolve each `matchup` slug's flag image. Two slugs, home first.
let matchup;
if (Array.isArray(spec.matchup) && spec.matchup.length === 2) {
  try {
    const pair = [];
    for (let m = 0; m < 2; m++) {
      const slug = spec.matchup[m];
      const ent = JSON.parse(fs.readFileSync(path.join(repoRoot, "kb/entities", `${slug}.json`), "utf8"));
      if (!ent.image?.url) throw new Error(`${slug} has no image`);
      const ext = (ent.image.url.split(".").pop() || "png").split("?")[0].slice(0, 4);
      const img = await download(ent.image.url, `matchup-${m}.${ext}`);
      // 3-letter team CODE for the scoreboard: prefer an explicit `code`, else an uppercase
      // short alias (<=3 chars, e.g. "USA"), else the first 3 letters of the name.
      const aliasCode = (ent.aliases || []).find((x) => /^[A-Za-z]{2,3}$/.test(x));
      const code = (ent.code || aliasCode || (ent.name || slug).slice(0, 3)).toUpperCase();
      pair.push({ img, name: ent.name || slug, code });
    }
    matchup = pair;
    console.log(`  matchup badge: ${pair.map((p) => p.name).join(" vs ")}`);
  } catch (e) { console.log(`matchup badge failed: ${String(e).split("\n")[0].slice(0, 60)}`); }
}

const out = {
  topic: assetsProps.topic,
  comment_bait: stripEmoji(assetsProps.comment_bait),
  cta: assetsProps.cta,
  handle: "@tikitakafootytv",
  scenes,
  ...(matchup ? { matchup } : {}),
  ...(sticker ? { sticker } : {}),
  ...(outro ? { outro } : {}),
  ...(endCard ? { endCard } : {}),
};
const outName = STORYBOARD ? "storyboard-props.json" : "props.json";
fs.writeFileSync(path.join(__dirname, outName), JSON.stringify(out, null, 2));
const withBg = scenes.filter((s) => s.bg || s.bgVideo).length;
console.log(`\nprepared ${scenes.length} scenes (${stem}); ${withBg} with backgrounds -> ${outName}`);
