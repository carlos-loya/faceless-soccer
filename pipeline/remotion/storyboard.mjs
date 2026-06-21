// Storyboard HTML generator. Reads storyboard-props.json (written by `prepare.mjs` in
// TTV_STORYBOARD mode — the SAME resolver the render uses, so it's faithful) + the spec, and
// emits a self-contained out/storyboards/<stem>.html: one 9:16 phone card per scene showing the
// ACTUAL resolved background with the caption over it, the VO line, the planned visual source,
// the running score, and any WARNINGS (image didn't resolve, `ai` not wired, stock_video freeze
// risk, missing matchup flag). The point: see exactly what the draft will look like — which is
// why the owner can fix the spec and re-run this (free, seconds) before paying for a slow render.
//
// Usage: node storyboard.mjs <stem>     (run from pipeline/remotion/, after prepare.mjs storyboard mode)
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../");
const stem = process.argv[2];
if (!stem) { console.error("usage: node storyboard.mjs <stem>"); process.exit(1); }

const props = JSON.parse(fs.readFileSync(path.join(__dirname, "storyboard-props.json"), "utf8"));
const specPath = path.join(repoRoot, "out/specs", `${stem}.json`);
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Images live in pipeline/remotion/public/<stem>/…; the HTML lives in out/storyboards/. Reference
// them with a relative path that resolves when the file is opened straight from disk.
const asset = (rel) => rel ? `../../pipeline/remotion/public/${esc(rel)}` : null;

// ---- per-scene cards -------------------------------------------------------
const FREEZE_LIMIT = 6; // curated stock_video clips are ~6s and don't loop → a longer beat freezes.
const cards = props.scenes.map((s, i) => {
  const n = i + 1;
  const warnings = [];
  const src = s.visual_source || "graphic";
  const hasBg = !!(s.bg || s.bgVideo);

  if (src === "ai") warnings.push("AI background not wired yet → renders with NO background. Use entity/commons/stock_video instead, or accept a plain card.");
  else if (src !== "graphic" && !hasBg) warnings.push(`'${src}: ${s.visual_query || "?"}' did not resolve → this scene renders on a plain brand graphic. Check the slug/query, or curate the entity.`);
  if (src === "stock_video" && s.bgVideo && (s.seconds || 0) >= FREEZE_LIMIT)
    warnings.push(`Planned ${s.seconds}s ≥ ~${FREEZE_LIMIT}s clip length → the b-roll may FREEZE on its last frame. Shorten the VO or pick a longer clip.`);
  if (Array.isArray(s.group_table) && spec.scenes[i]?.group_table && s.group_table.length < spec.scenes[i].group_table.length)
    warnings.push(`Group table: only ${s.group_table.length}/${spec.scenes[i].group_table.length} rows resolved (a nation is missing a flag image).`);
  if ((s.graphic_type === "scorers_split" || s.graphic_type === "comparison_split") && Array.isArray(s.vsImages) && s.vsImages.some((f) => !f))
    warnings.push("A vs-split side has no flag image (renders a silhouette/blank). Check the on-screen 'A vs B' labels match KB slugs.");

  // SCENE 2 is the retention cliff (41% of videos leak hardest here) — it MUST escalate the hook.
  // Heuristic deflate-detector + an always-on audit reminder (see videospec rule 1b).
  let auditHtml = "";
  if (i === 1) {
    const t2 = `${s.on_screen_text || ""} ${s.voiceover || ""}`;
    const timeline = /\b\d{1,3}\s*['′’]/.test(t2) || /\b\d{1,2}\s*[-–]\s*\d{1,2}\b/.test(t2); // "20'" / "1-0"
    if (timeline)
      warnings.push("SCENE 2 looks like a chronological timeline (a minute mark or scoreline). Scene 2 is the #1 retention cliff — make it ESCALATE the hook's stakes, don't narrate the clock (videospec rule 1b).");
    auditHtml = `<div class="audit">⚠ AUDIT scene 2 (retention cliff): does this ESCALATE the hook, or hand the story to the opponent / go abstract / narrate the clock? Raise the subject's specific stake.</div>`;
  }

  const media = s.bgVideo
    ? `<video class="bg" src="${asset(s.bgVideo)}" muted autoplay loop playsinline></video>`
    : s.bg
      ? `<img class="bg" src="${asset(s.bg)}" alt="">`
      : `<div class="bg nobg">no background<br><small>brand graphic</small></div>`;

  const scoreBadge = s.score ? `<span class="score">${esc(s.score)}</span>` : "";
  const subBadge = (s.subscribe_chip || spec.scenes[i]?.subscribe_chip) ? `<span class="subchip">▶ SUB CHIP</span>` : "";
  // Only per-scene FLAG stickers render now (the subject/foil corner cutouts were removed).
  const stickerImg = s.sticker?.flag ? `<img class="sticker" src="${asset(s.sticker.img)}" alt="">` : "";
  const creditLine = s.credit ? `<div class="credit">${esc(s.credit)}</div>` : "";
  const warnHtml = warnings.length
    ? `<ul class="warn">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>`
    : `<div class="ok">✓ resolved</div>`;

  return `
  <div class="card">
    <div class="phone">
      ${media}
      ${stickerImg}
      <div class="topbar"><span class="num">#${n}</span><span class="gt">${esc(s.graphic_type || "graphic")}</span>${subBadge}${scoreBadge}</div>
      <div class="cap">${esc(s.on_screen_text)}</div>
      ${creditLine}
    </div>
    <div class="meta">
      <div class="src ${hasBg ? "got" : "miss"}">${esc(src)}${s.visual_query ? " · " + esc(s.visual_query) : ""}</div>
      <div class="vo">“${esc(s.voiceover || "")}”</div>
      <div class="dur">~${s.seconds}s (planned)</div>
      ${warnHtml}
      ${auditHtml}
    </div>
  </div>`;
}).join("\n");

// ---- header / global checks ------------------------------------------------
const headerWarn = [];
if (Array.isArray(spec.matchup) && spec.matchup.length === 2 && !(Array.isArray(props.matchup) && props.matchup.length === 2))
  headerWarn.push(`Matchup [${spec.matchup.join(", ")}] did not fully resolve → the scoreboard/VS badge will NOT render (a nation entity is missing a flag image).`);

// Subscribe capture (videospec rule 5): exactly one beat — the climax — should carry subscribe_chip.
const chipCount = (spec.scenes || []).filter((sc) => sc.subscribe_chip).length;
if (chipCount === 0)
  headerWarn.push(`No scene has subscribe_chip → no SUBSCRIBE pill will show. Set subscribe_chip:true on the CLIMAX beat + weave a subject-tied subscribe line into its voiceover (videospec rule 5).`);
else if (chipCount > 1)
  headerWarn.push(`${chipCount} scenes have subscribe_chip — use exactly ONE (the climax).`);

const totalPlanned = props.scenes.reduce((t, s) => t + (s.seconds || 0), 0);
const matchHdr = Array.isArray(props.matchup) && props.matchup.length === 2
  ? props.matchup.map((m) => `<span class="flag"><img src="${asset(m.img)}" alt="">${esc(m.code || m.name)}</span>`).join('<span class="vs">vs</span>')
  : "";

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Storyboard · ${esc(stem)}</title>
<style>
  :root { --gold:#F7D774; --gold2:#C8881B; --bg:#0b0b0c; --panel:#161618; --line:#2a2a2e; --warn:#ff8a5c; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:#eee; font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:20px 24px; border-bottom:1px solid var(--line); position:sticky; top:0; background:rgba(11,11,12,.96); backdrop-filter:blur(6px); z-index:5; }
  h1 { margin:0 0 4px; font-size:18px; color:var(--gold); letter-spacing:.3px; }
  h1 small { color:#888; font-weight:400; }
  .topic { color:#bbb; max-width:900px; }
  .hdrline { display:flex; gap:18px; align-items:center; flex-wrap:wrap; margin-top:10px; color:#ccc; }
  .flag img { height:20px; vertical-align:middle; margin-right:5px; border:1px solid #333; }
  .vs { color:var(--gold); margin:0 8px; font-weight:700; }
  .badge { background:var(--panel); border:1px solid var(--line); border-radius:999px; padding:3px 12px; color:#ddd; }
  .hwarn { margin:12px 0 0; padding:10px 14px; border-left:3px solid var(--warn); background:#1c130d; color:#ffd9c4; border-radius:4px; }
  .hwarn li { margin:2px 0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:22px; padding:24px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  .phone { position:relative; aspect-ratio:9/16; background:#000; overflow:hidden; }
  .bg { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .nobg { display:flex; flex-direction:column; align-items:center; justify-content:center; color:#555; text-align:center; background:repeating-linear-gradient(45deg,#111,#111 10px,#141414 10px,#141414 20px); }
  .sticker { position:absolute; top:8px; right:8px; height:64px; width:64px; object-fit:contain; filter:drop-shadow(0 2px 6px #000); z-index:3; }
  .topbar { position:absolute; top:0; left:0; right:0; display:flex; align-items:center; gap:8px; padding:8px; z-index:2; }
  .num { background:var(--gold); color:#000; font-weight:800; border-radius:6px; padding:2px 8px; font-size:13px; }
  .gt { background:rgba(0,0,0,.6); color:#cfcfcf; border-radius:6px; padding:2px 8px; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
  .score { margin-left:auto; background:#000; color:var(--gold); font-weight:800; border:1px solid var(--gold2); border-radius:6px; padding:2px 9px; }
  .cap { position:absolute; left:0; right:0; bottom:0; padding:14px 12px 16px; background:linear-gradient(transparent,rgba(0,0,0,.85)); font-weight:800; font-size:17px; text-shadow:0 2px 6px #000; line-height:1.2; }
  .credit { position:absolute; left:6px; bottom:2px; font-size:8px; color:#9a9a9a; z-index:2; }
  .meta { padding:12px 14px; }
  .src { display:inline-block; font-weight:700; font-size:12px; border-radius:6px; padding:2px 8px; margin-bottom:8px; }
  .src.got { background:#10331d; color:#7fe0a0; }
  .src.miss { background:#3a1410; color:#ff9b86; }
  .vo { color:#cfcfcf; font-style:italic; margin-bottom:6px; }
  .dur { color:#888; font-size:12px; margin-bottom:8px; }
  .warn { margin:0; padding-left:18px; color:#ffcdb6; }
  .warn li { margin:4px 0; }
  .ok { color:#6fbf8a; font-size:12px; }
  .audit { margin-top:8px; padding:8px 10px; border-left:3px solid var(--gold2); background:#1a1505; color:#f0d79a; border-radius:4px; font-size:12px; }
  .subchip { margin-left:auto; background:var(--gold); color:#111; font-weight:800; border-radius:6px; padding:2px 9px; font-size:11px; }
  footer { padding:18px 24px 40px; color:#999; border-top:1px solid var(--line); }
  footer b { color:var(--gold); }
</style></head>
<body>
<header>
  <h1>Storyboard <small>· ${esc(stem)} · ${props.scenes.length} scenes · ~${Math.round(totalPlanned)}s planned</small></h1>
  <div class="topic">${esc(props.topic)}</div>
  <div class="hdrline">
    <span class="badge">format: ${esc(spec.format || "?")}</span>
    ${matchHdr ? `<span>${matchHdr}</span>` : ""}
  </div>
  ${headerWarn.length ? `<ul class="hwarn">${headerWarn.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
</header>
<div class="grid">
${cards}
</div>
<footer>
  <p><b>Comment-bait:</b> ${esc(props.comment_bait)}</p>
  <p>This is a NO-VO, NO-RENDER preview built from the exact same resolver the draft uses — every background here is what the render will fetch. Fix any wrong <code>visual_source</code>/<code>visual_query</code> in <code>out/specs/${esc(stem)}.json</code>, re-run <code>/storyboard</code> (free, seconds), then render the draft once it looks right.</p>
</footer>
</body></html>`;

const outDir = path.join(repoRoot, "out/storyboards");
fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, `${stem}.html`);
fs.writeFileSync(outFile, html);

// Machine-readable summary for the slash command to report without re-parsing HTML.
const summary = {
  stem,
  scenes: props.scenes.map((s, i) => ({
    n: i + 1, source: s.visual_source || "graphic", query: s.visual_query || "",
    resolved: !!(s.bg || s.bgVideo), kind: s.bgVideo ? "video" : s.bg ? "image" : "none",
    seconds: s.seconds, graphic_type: s.graphic_type || "",
  })),
  unresolved: props.scenes.filter((s) => (s.visual_source && s.visual_source !== "graphic" && s.visual_source !== "ai") && !(s.bg || s.bgVideo)).length,
  header_warnings: headerWarn,
  html: path.relative(repoRoot, outFile),
};
fs.writeFileSync(path.join(outDir, `${stem}.summary.json`), JSON.stringify(summary, null, 2));

console.log(`✓ storyboard -> ${path.relative(repoRoot, outFile)}`);
console.log(`  ${summary.scenes.filter((s) => s.resolved).length}/${summary.scenes.length} scenes have a background; ${summary.unresolved} unresolved; ${headerWarn.length} header warning(s)`);
