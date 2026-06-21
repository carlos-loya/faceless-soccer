import React from "react";
import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, staticFile, interpolate, spring,
  useCurrentFrame, useVideoConfig, Easing,
} from "remotion";
import { fitText } from "@remotion/layout-utils";
import { CountUp, parseCount } from "./CountUp";
import { RankingRow } from "./RankingRow";
import { QuizReveal } from "./QuizReveal";
import { KineticHeadline } from "./KineticHeadline";
import { VsSplit } from "./VsSplit";
import { ScorersSplit } from "./ScorersSplit";

export const FPS = 30;
export const framesFor = (seconds: number) => Math.round((seconds || 3) * FPS);

const GOLD = "linear-gradient(180deg,#F7D774,#C8881B)";
// SAFE AREA — keep all text/graphics clear of the platform UI overlays (YouTube Shorts /
// Reels / TikTok): the bottom holds the caption/title + progress bar, and the lower-RIGHT
// holds the like/comment/share rail. So reserve a tall bottom margin and a bigger RIGHT
// margin (text biased slightly left to dodge the action buttons).
const SAFE_W = 830;        // max text width (was 900) — narrower so lines clear the side rails
const PAD_L = 80;          // left margin
const PAD_R = 170;         // right margin — wider, clears the action-button rail
const SAFE_TOP = 200;      // top reserve — lowered watermark/credit sit in this band, clear of YouTube's top bar/gradient on phones
const SAFE_BOTTOM = 440;   // bottom reserve — clears the caption/title + progress bar (~23%)
const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";
const COMP_H = 1920;       // composition height (9:16)
const SCOREBOARD_TOP = 1180; // running scoreboard sits CENTERED in the lower-middle (clear of faces up top); captions reserve space above it
const SB_CAP_GAP = 40;     // min gap between the captions above and the scoreboard below

type Word = { word: string; start: number; end: number };
type Scene = {
  on_screen_text: string;
  stat_callout: string;
  graphic_type?: string;
  audioFile: string;
  seconds: number;
  words?: Word[];    // per-word VO timings -> karaoke captions
  camera?: string;   // camera move for a still-image bg (push_in/pull_out/pan_left/pan_right/tilt_up/tilt_down/ken_burns)
  bg?: string;       // per-scene background image (staticFile path)
  bgVideo?: string;  // per-scene background VIDEO (stock_video b-roll; staticFile path)
  credit?: string;   // attribution for that image (CC / Pexels)
  sticker?: { img: string; flag?: boolean; cutout?: boolean; name?: string };  // per-scene corner sticker (flag chip, or a player cutout)
  score?: string;    // running scoreboard score for this beat, "HOME-AWAY" (match summaries)
  group_table?: GroupRow[];  // ranked group-standings table for this beat (hides the scoreboard here)
  subscribe_chip?: boolean;  // pop a small "SUBSCRIBE" pill overlay on THIS beat (the climax) for ~2s
};
type GroupRow = { code: string; flag: string; name?: string; points: number; played?: number | null; gd?: number | null; highlight?: boolean };
type Props = {
  topic: string;
  comment_bait: string;
  cta: string;
  handle: string;
  scenes: Scene[];
  sticker?: { img: string; name: string; cutout?: boolean };  // subject pinned in the corner
  outro?: { audioFile: string; seconds: number };             // spoken comment-bait on the end card
  endCard?: { bgVideo?: string; credit?: string };            // atmosphere bg behind the comment-bait card
  matchup?: { img: string; name: string; code?: string }[];   // 2 flags -> persistent top-left badge: a running SCOREBOARD if scenes carry `score`, else a "VS" badge
};

const goldText: React.CSSProperties = {
  backgroundImage: GOLD,
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  color: "transparent",
};

const accentFor = (s: Scene): string | null => {
  const t = (s.on_screen_text + " " + s.stat_callout).toLowerCase();
  if (t.includes("champions")) return "linear-gradient(135deg,#A50044,#004D98)";
  if (t.includes("spain") || t.includes("euro")) return "#C8102E";
  return null;
};

// Directed camera move over a still-image bg (the "cinematography" layer). Each move maps the
// scene's progress p∈[0,1] -> {scale, tx%, ty%}. Scale stays >1 the whole time so a pan/tilt
// never reveals a black edge (at scale 1.22 there's ~11% overflow each side; moves stay within ±6%).
// `dir` alternates ken_burns by scene index so consecutive Ken-Burns scenes don't mirror.
// A directed camera move over a still-image bg, done with objectPosition (pan/tilt WITHIN the
// cover-crop, so it never reveals a black edge AND the travel auto-scales to the image's aspect:
// a wide landscape pans across its whole width, a portrait barely moves) + scale (the zoom).
// posX/posY are objectPosition %: 0 = left/top edge of the image, 100 = right/bottom, 50 = center.
const cameraMove = (move: string, p: number, dir: number): { scale: number; posX: number; posY: number } => {
  const lerp = (a: number, b: number) => interpolate(p, [0, 1], [a, b]);
  switch (move) {
    case "push_in":   return { scale: lerp(1.05, 1.28), posX: 50, posY: 50 };
    case "pull_out":  return { scale: lerp(1.30, 1.06), posX: 50, posY: 50 };
    case "pan_left":  return { scale: 1.06, posX: lerp(72, 8),  posY: 50 };  // drift to the image's LEFT (e.g. a left-side sign)
    case "pan_right": return { scale: 1.06, posX: lerp(28, 92), posY: 50 };  // drift to the RIGHT
    case "tilt_up":   return { scale: 1.06, posX: 50, posY: lerp(72, 8) };   // drift to the TOP
    case "tilt_down": return { scale: 1.06, posX: 50, posY: lerp(28, 92) };  // drift to the BOTTOM
    case "ken_burns":
    default:          return { scale: lerp(1.08, 1.22), posX: lerp(50 - 3 * dir, 50 + 3 * dir), posY: lerp(50 + 3 * dir, 50 - 3 * dir) };
  }
};

// GLOBAL COLOR GRADE — applied to EVERY background (player photo + stock video) so disparate
// sources (a clean studio portrait vs gritty night b-roll) share ONE look: punchier contrast,
// desaturated so stray colours (a green pitch, a blue night sky) stop fighting the brand, slightly
// moodier, with a faint warm/gold cast toward the palette. This is the single biggest cohesion lever.
const GRADE = "contrast(1.12) saturate(0.8) brightness(0.9) sepia(0.14)";

const CameraMove: React.FC<{ src: string; durationFrames: number; dir: number; move?: string }> = ({ src, durationFrames, dir, move }) => {
  const frame = useCurrentFrame();
  const p = Math.min(frame / durationFrames, 1);
  const { scale, posX, posY } = cameraMove(move || "ken_burns", p, dir);
  return (
    <AbsoluteFill>
      <Img src={staticFile(src)} style={{
        width: "100%", height: "100%", objectFit: "cover", objectPosition: `${posX}% ${posY}%`,
        transform: `scale(${scale})`, filter: GRADE,
      }} />
    </AbsoluteFill>
  );
};

// Moving stock b-roll background (muted) — generic atmosphere only. Curated clips are ~6s and
// OffthreadVideo holds its LAST frame once the clip ends, so a scene MUST stay shorter than its
// clip or it freezes. The VO drives scene length, so keep per-scene voiceover tight enough that
// the beat fits inside the ~6s clip (OffthreadVideo has no `loop` in this Remotion version). Same GRADE as photos.
const VideoBg: React.FC<{ src: string }> = ({ src }) => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile(src)} muted
      style={{ width: "100%", height: "100%", objectFit: "cover", filter: GRADE }} />
  </AbsoluteFill>
);

// Static film-grain texture (tiny SVG noise, tiled) — "averages" mismatched footage so stock and
// portraits read as one piece. Subtle, soft-light blend. The classic editor cohesion trick.
const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'>" +
  "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/>" +
  "</filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")";

// The unified BRAND SCRIM over every background: (1) bottom-heavy legibility gradient, (2) a
// vignette focusing the centre + hiding the "stockness" at the edges, (3) a faint gold tint that
// pulls every scene toward the palette, (4) a film-grain pass to tie disparate sources together.
// One injection point — runs on every bg scene AND the end card — so the whole channel shares a look.
const DarkOverlay: React.FC = () => (
  <>
    <AbsoluteFill style={{
      background: "linear-gradient(180deg,rgba(10,10,11,0.45) 0%,rgba(10,10,11,0.30) 38%,rgba(10,10,11,0.86) 100%)",
    }} />
    <AbsoluteFill style={{
      background: "radial-gradient(ellipse 78% 66% at 50% 42%, transparent 46%, rgba(0,0,0,0.55) 100%)",
    }} />
    <AbsoluteFill style={{
      background: "radial-gradient(circle at 50% 30%, rgba(247,215,116,0.10), transparent 62%)",
      mixBlendMode: "soft-light",
    }} />
    <AbsoluteFill style={{
      backgroundImage: GRAIN, backgroundRepeat: "repeat", backgroundSize: "140px 140px",
      opacity: 0.10, mixBlendMode: "overlay",
    }} />
  </>
);

// Pinned TOP-CENTER (in the SAFE_TOP band): horizontally centered near the top, clear of the
// karaoke captions + stats that fill the bottom/middle.
const Watermark: React.FC = () => (
  <div style={{
    position: "absolute", top: 150, left: 0, right: 0, textAlign: "center",
    fontWeight: 800, letterSpacing: 3, fontSize: 30, textTransform: "uppercase",
    opacity: 0.85, textShadow: "0 2px 12px rgba(0,0,0,0.6)", ...goldText,
  }}>TikiTakaFootyTV</div>
);

// Image/footage attribution — tucked just UNDER the top-left watermark, kept small.
// The scoreboard/badge now sit ~1/3 down (well below), so the credit always rides under
// the watermark regardless of whether a matchup is shown.
const Credit: React.FC<{ text: string; top?: number }> = ({ text, top = 196 }) => (
  <div style={{
    position: "absolute", top, left: PAD_L, maxWidth: 520, textAlign: "left",
    fontSize: 13, opacity: 0.5, color: "#fff", fontFamily: "'Helvetica Neue',Arial,sans-serif",
    textShadow: "0 1px 5px rgba(0,0,0,0.75)", lineHeight: 1.2,
  }}>{text}</div>
);

// Persistent head-to-head badge: two flag chips + "VS", pinned top-left UNDER the watermark,
// shown for the whole video. For match preview/recap videos (spec `matchup`: two flag entities).
const MatchupBadge: React.FC<{ pair: { img: string; name: string }[] }> = ({ pair }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 16, stiffness: 120 } });
  const pop = interpolate(s, [0, 1], [0.7, 1]);
  const chip = (img: string) => (
    <div style={{
      padding: 5, background: "#fff", borderRadius: 12, boxShadow: "0 6px 16px rgba(0,0,0,0.55)",
    }}>
      <Img src={staticFile(img)} style={{ width: 150, height: 100, objectFit: "cover", borderRadius: 7, display: "block" }} />
    </div>
  );
  return (
    // CENTERED in the lower-middle (mirrors the Scoreboard position): below the captions, clear of
    // player faces up top, enlarged for thumbnail legibility. Spans the content scenes only — the
    // calling component hides it on the comment-bait end card.
    <div style={{
      position: "absolute", top: SCOREBOARD_TOP, left: "50%", zIndex: 45,
      display: "flex", alignItems: "center", gap: 22,
      transform: `translateX(-50%) scale(${pop})`, transformOrigin: "center top",
    }}>
      {chip(pair[0].img)}
      <div style={{ fontWeight: 900, fontSize: 54, letterSpacing: 1, ...goldText,
        textShadow: "0 2px 8px rgba(0,0,0,0.7)" }}>VS</div>
      {chip(pair[1].img)}
    </div>
  );
};

// Persistent broadcast SCOREBOARD (top-left, under the watermark) for match-summary videos:
// a TV-bug pill — flag + 3-letter code on each side, the running score in the middle, ticking
// up as the story is told. Driven by a per-scene `timeline` (cumulative frame offsets + the
// score in force at that beat); the score POPS + flashes gold the moment a goal goes in.
type ScoreEntry = { fromFrame: number; home: number; away: number };
const Scoreboard: React.FC<{ pair: { img: string; name: string; code?: string }[]; timeline: ScoreEntry[]; hidden?: { from: number; to: number }[] }> = ({ pair, timeline, hidden }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Hidden on group-table / wrap-up beats (and on the comment-bait card, via its Sequence span).
  if (hidden?.some((h) => frame >= h.from && frame < h.to)) return null;
  const intro = spring({ frame, fps, config: { damping: 16, stiffness: 120 } });
  const introPop = interpolate(intro, [0, 1], [0.7, 1]);
  // Active entry = the last one whose start frame has passed (holds the final score on the end card).
  let idx = 0;
  for (let i = 0; i < timeline.length; i++) { if (timeline[i].fromFrame <= frame) idx = i; else break; }
  const cur = timeline[idx] || { fromFrame: 0, home: 0, away: 0 };
  const prev = idx > 0 ? timeline[idx - 1] : null;
  const changed = !!prev && (prev.home !== cur.home || prev.away !== cur.away);
  const since = frame - cur.fromFrame;
  // Goal pop + gold flash, only when the score just changed.
  const goalSpring = changed ? spring({ frame: Math.max(0, since), fps, config: { damping: 10, stiffness: 200 } }) : 1;
  const goalPop = changed ? interpolate(goalSpring, [0, 1], [1.55, 1]) : 1;
  const flash = changed ? interpolate(since, [0, 6, 18], [0.85, 0.5, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;

  const chip = (img: string) => (
    <div style={{ padding: 4, background: "#fff", borderRadius: 9, boxShadow: "0 5px 14px rgba(0,0,0,0.55)" }}>
      <Img src={staticFile(img)} style={{ width: 84, height: 56, objectFit: "cover", borderRadius: 5, display: "block" }} />
    </div>
  );
  const codeStyle: React.CSSProperties = {
    fontFamily: FONT, fontWeight: 800, fontSize: 50, letterSpacing: 1, color: "#fff",
    textShadow: "0 2px 8px rgba(0,0,0,0.85)",
  };
  const codeOf = (p: { name: string; code?: string }) => (p.code || p.name.slice(0, 3)).toUpperCase();
  return (
    // CENTERED in the lower-middle of the screen (below the captions, clear of player faces up
    // top), enlarged — big enough to read at a glance in a thumbnail. Same fixed spot every scene.
    <div style={{
      position: "absolute", top: SCOREBOARD_TOP, left: "50%", zIndex: 45,
      display: "flex", alignItems: "center", gap: 18, padding: "14px 24px", borderRadius: 20,
      background: "rgba(10,10,11,0.72)", border: "1.5px solid rgba(247,215,116,0.4)",
      boxShadow: "0 10px 28px rgba(0,0,0,0.55)",
      transform: `translateX(-50%) scale(${introPop})`, transformOrigin: "center top",
    }}>
      {chip(pair[0].img)}
      <div style={codeStyle}>{codeOf(pair[0])}</div>
      <div style={{ position: "relative", padding: "0 3px" }}>
        <div style={{ position: "absolute", inset: -12, borderRadius: 14,
          background: "radial-gradient(circle, rgba(247,215,116,0.9), transparent 70%)", opacity: flash }} />
        <div style={{
          position: "relative", fontFamily: FONT, fontWeight: 800, fontSize: 68, lineHeight: 1,
          whiteSpace: "nowrap", transform: `scale(${goalPop})`, transformOrigin: "center",
          ...goldText, textShadow: "0 2px 8px rgba(0,0,0,0.85)",
        }}>{cur.home}<span style={{ margin: "0 9px", opacity: 0.7 }}>-</span>{cur.away}</div>
      </div>
      <div style={codeStyle}>{codeOf(pair[1])}</div>
      {chip(pair[1].img)}
    </div>
  );
};

// Group-standings TABLE for a match-day wrap-up beat: position + flag + code + points (and
// optional P / GD columns). Rows stagger in; the video's team highlights gold. The running
// scoreboard is auto-hidden on any scene that shows this (see TikiTakaVideo).
const GroupTable: React.FC<{ rows: GroupRow[]; title?: string }> = ({ rows, title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const anyGd = rows.some((r) => r.gd !== undefined && r.gd !== null);
  const anyP = rows.some((r) => r.played !== undefined && r.played !== null);
  const label: React.CSSProperties = { fontFamily: FONT, fontWeight: 700, fontSize: 30, color: "#fff", letterSpacing: 1 };
  return (
    <div style={{ width: SAFE_W, display: "flex", flexDirection: "column", gap: 13, zIndex: 30 }}>
      {title ? (
        <div style={{
          fontFamily: FONT, fontWeight: 800, fontSize: 58, letterSpacing: 2, textTransform: "uppercase",
          textAlign: "center", marginBottom: 6, ...goldText, textShadow: "0 3px 16px rgba(0,0,0,0.9)",
        }}>{title}</div>
      ) : null}
      <div style={{ display: "flex", alignItems: "center", padding: "0 26px", opacity: 0.6, ...label }}>
        <div style={{ width: 56 }}>#</div>
        <div style={{ flex: 1 }}>TEAM</div>
        {anyP ? <div style={{ width: 70, textAlign: "center" }}>P</div> : null}
        {anyGd ? <div style={{ width: 96, textAlign: "center" }}>GD</div> : null}
        <div style={{ width: 96, textAlign: "center" }}>PTS</div>
      </div>
      {rows.map((r, i) => {
        const s = spring({ frame: Math.max(0, frame - 4 - i * 5), fps, config: { damping: 16, stiffness: 130 } });
        const x = interpolate(s, [0, 1], [60, 0]);
        const op = interpolate(s, [0, 1], [0, 1]);
        const hl = r.highlight;
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center", padding: "13px 26px", borderRadius: 16,
            transform: `translateX(${x}px)`, opacity: op,
            background: hl ? "rgba(247,215,116,0.16)" : "rgba(10,10,11,0.66)",
            border: hl ? "2px solid rgba(247,215,116,0.85)" : "1.5px solid rgba(255,255,255,0.12)",
            boxShadow: "0 8px 22px rgba(0,0,0,0.5)",
          }}>
            <div style={{ width: 56, fontFamily: FONT, fontWeight: 800, fontSize: 46, color: hl ? "#F7D774" : "#fff" }}>{i + 1}</div>
            <div style={{ padding: 3, background: "#fff", borderRadius: 7, marginRight: 18, boxShadow: "0 4px 12px rgba(0,0,0,0.5)" }}>
              <Img src={staticFile(r.flag)} style={{ width: 70, height: 47, objectFit: "cover", borderRadius: 4, display: "block" }} />
            </div>
            <div style={{ flex: 1, fontFamily: FONT, fontWeight: 800, fontSize: 50, letterSpacing: 1, color: "#fff", textShadow: "0 2px 8px rgba(0,0,0,0.85)" }}>{r.code}</div>
            {anyP ? <div style={{ width: 70, textAlign: "center", fontFamily: FONT, fontWeight: 700, fontSize: 44, color: "#fff" }}>{r.played ?? "-"}</div> : null}
            {anyGd ? <div style={{ width: 96, textAlign: "center", fontFamily: FONT, fontWeight: 700, fontSize: 44, color: "#fff" }}>{r.gd == null ? "-" : (r.gd > 0 ? `+${r.gd}` : r.gd)}</div> : null}
            <div style={{ width: 96, textAlign: "center", fontFamily: FONT, fontWeight: 800, fontSize: 50, ...goldText }}>{r.points}</div>
          </div>
        );
      })}
    </div>
  );
};

// Per-scene flag sticker: a white-bordered rounded flag chip, tilted, pinned top-right.
const FlagSticker: React.FC<{ img: string }> = ({ img }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 14, stiffness: 120 } });
  const pop = interpolate(s, [0, 1], [0.5, 1]);
  const rot = interpolate(s, [0, 1], [-12, -6]);
  return (
    <div style={{
      position: "absolute", top: 30, right: 30, transformOrigin: "top right",
      transform: `scale(${pop}) rotate(${rot}deg)`, zIndex: 40,
      padding: 7, background: "#fff", borderRadius: 16,
      boxShadow: "0 12px 26px rgba(0,0,0,0.55)",
    }}>
      <Img src={staticFile(img)} style={{
        width: 220, height: 146, objectFit: "cover", borderRadius: 9, display: "block",
      }} />
    </div>
  );
};

// Karaoke captions (option A — carries the spoken line). Shows the VO a short line at a time,
// highlighting the word as it's spoken (gold), past words solid white, upcoming words dimmed.
// Word times are seconds relative to this scene's audio (the Sequence resets frame to 0).
const PER_LINE = 4;
const Karaoke: React.FC<{ words: Word[]; shadow: string }> = ({ words, shadow }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  // Active = the last word whose start has passed (stays lit during the gaps between words).
  let active = 0;
  for (let i = 0; i < words.length; i++) { if (words[i].start <= t) active = i; else break; }
  const started = t >= (words[0]?.start ?? 0);
  const lineIdx = Math.min(Math.floor(active / PER_LINE), Math.ceil(words.length / PER_LINE) - 1);
  const line = words.slice(lineIdx * PER_LINE, lineIdx * PER_LINE + PER_LINE);
  return (
    <div style={{
      position: "relative", marginTop: 64, display: "flex", flexWrap: "wrap",
      justifyContent: "center", alignItems: "baseline", gap: "6px 16px", maxWidth: SAFE_W,
    }}>
      {line.map((w, k) => {
        const gi = lineIdx * PER_LINE + k;
        const isActive = started && gi === active;
        const isPast = gi < active;
        return (
          <span key={gi} style={{
            fontFamily: FONT, fontWeight: 800, fontSize: 70, lineHeight: 1.0,
            letterSpacing: 1, textTransform: "uppercase",
            transform: isActive ? "scale(1.06)" : "scale(1)",
            transition: "none", textShadow: shadow,
            ...(isActive ? goldText : { color: "#fff", opacity: isPast ? 1 : 0.4 }),
          }}>{w.word}</span>
        );
      })}
    </div>
  );
};

const Card: React.FC<{ scene: Scene; durationFrames: number; dir: number; index: number; creditTop?: number; hasScoreboard?: boolean; hasMatchupBadge?: boolean }> = ({ scene, durationFrames, dir, index, creditTop, hasScoreboard, hasMatchupBadge }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // When the running scoreboard OR the flag-VS badge shows on this beat (both sit centered in the
  // lower-middle; group-table scenes hide the scoreboard), reserve that band so the captions sit
  // ABOVE the lower element, never over it.
  const lowerBadgeActive = (!!hasScoreboard || !!hasMatchupBadge) && !scene.group_table?.length;
  const padBottom = lowerBadgeActive ? COMP_H - SCOREBOARD_TOP + SB_CAP_GAP : SAFE_BOTTOM;
  const s = spring({ frame, fps, config: { damping: 16, stiffness: 130 } });
  const pop = interpolate(s, [0, 1], [0.7, 1]);
  const rise = interpolate(s, [0, 1], [40, 0]);
  const flash = interpolate(frame, [0, 8, 24], [0, 0.5, 0], { extrapolateRight: "clamp" });
  const hasBg = !!(scene.bg || scene.bgVideo);
  // Bottom-anchor text ONLY over a player photo (keeps it below the face). Over video b-roll
  // (atmosphere — hook/guess/outro) or no bg, center it so it's not cramped at the bottom.
  const anchorBottom = !!scene.bg && !scene.bgVideo;
  const accent = accentFor(scene);
  const shadow = hasBg ? "0 4px 30px rgba(0,0,0,0.9)" : "none";
  // Auto-fit the big stat so ANY text stays on screen: shrink from the 300px design
  // size only as far as needed to fit the safe width.
  const statFontSize = scene.stat_callout
    ? Math.min(300, fitText({
        text: scene.stat_callout, withinWidth: SAFE_W,
        fontFamily: FONT, fontWeight: 800, letterSpacing: "-6px",
      }).fontSize)
    : 0;

  // Punch-in entrance (a lightweight scene "transition" with NO audio overlap): each scene's
  // whole frame slides + scales + fades in over ~6 frames. The bg is zoomed, so the slide
  // never reveals a black edge.
  const ip = interpolate(frame, [0, 6], [0, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const introX = interpolate(ip, [0, 1], [40 * dir, 0]);
  const introScale = interpolate(ip, [0, 1], [1.05, 1]);
  const introOp = interpolate(ip, [0, 1], [0.5, 1]);
  const isHook = index === 0;

  return (
    <AbsoluteFill style={{ opacity: introOp, transform: `translateX(${introX}px) scale(${introScale})` }}>
      {scene.bgVideo ? <VideoBg src={scene.bgVideo} />
        : scene.bg ? <CameraMove src={scene.bg} durationFrames={durationFrames} dir={dir} move={scene.camera} />
        : null}
      {hasBg && <DarkOverlay />}
      <AbsoluteFill style={{
        background: hasBg ? "transparent" : "radial-gradient(120% 90% at 50% 35%,#1C1C1E,#0A0A0B)",
        alignItems: "center", justifyContent: anchorBottom ? "flex-end" : "center",
        paddingTop: SAFE_TOP, paddingBottom: padBottom, paddingLeft: PAD_L, paddingRight: PAD_R,
        textAlign: "center",
        fontFamily: "'Arial Narrow','Helvetica Neue',Arial,sans-serif",
      }}>
        {accent && !hasBg && <AbsoluteFill style={{ background: accent, opacity: 0.18 }} />}
        <AbsoluteFill style={{
          background: "radial-gradient(circle at 50% 42%,rgba(247,215,116,0.4),transparent 60%)",
          opacity: flash,
        }} />
        {scene.group_table?.length ? (
          // Standings table with the VO karaoke captions stacked BELOW it (column, centered) so
          // the words never overlap the table. The whole stack is vertically centered in the card.
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18, maxWidth: SAFE_W }}>
            <GroupTable rows={scene.group_table} title={scene.on_screen_text} />
            {scene.words?.length ? <Karaoke words={scene.words} shadow={shadow} /> : null}
          </div>
        ) : scene.graphic_type === "ranking_row" ? (
          <RankingRow scene={scene} shadow={shadow} />
        ) : scene.graphic_type === "quiz_board" ? (
          <QuizReveal scene={scene} statFontSize={statFontSize} shadow={shadow} durationFrames={durationFrames} />
        ) : scene.graphic_type === "comparison_split" ? (
          <VsSplit scene={scene} statFontSize={statFontSize} shadow={shadow} />
        ) : scene.graphic_type === "scorers_split" ? (
          <ScorersSplit scene={scene} shadow={shadow} />
        ) : (
          <>
            {scene.stat_callout ? (
              <div style={{
                position: "relative", fontWeight: 800, fontSize: statFontSize, lineHeight: 0.9,
                letterSpacing: -6, whiteSpace: "nowrap", fontFamily: FONT, marginBottom: 28,
                transform: `scale(${pop})`, textShadow: shadow, ...goldText,
              }}>
                {(() => {
                  const c = parseCount(scene.stat_callout);
                  return c ? (
                    <CountUp
                      to={c.to} prefix={c.prefix} suffix={c.suffix}
                      durationFrames={Math.min(Math.round(fps * 1.1), durationFrames - 6)}
                    />
                  ) : scene.stat_callout;
                })()}
              </div>
            ) : null}
            {isHook ? (
              // The hook keeps its bold sound-off headline (win the first second); no karaoke here.
              <KineticHeadline text={scene.on_screen_text} shadow={shadow} />
            ) : scene.words?.length ? (
              // Body beats: karaoke captions carry the spoken line (option A).
              <Karaoke words={scene.words} shadow={shadow} />
            ) : (
              <div style={{
                position: "relative", marginTop: 60, fontWeight: 800, fontSize: 84,
                lineHeight: 1.05, letterSpacing: 1, textTransform: "uppercase", color: "#fff",
                maxWidth: SAFE_W, transform: `translateY(${rise}px)`, textShadow: shadow,
              }}>{scene.on_screen_text}</div>
            )}
          </>
        )}
        <Watermark />
      </AbsoluteFill>
      {/* Corner stickers disabled entirely (owner preference, 2026-06-14): no subject cutout
          and no per-scene flag chip. The matchup scoreboard/VS badge already carries the flags,
          so a corner sticker is redundant and crowds the frame. (FlagSticker + Props.sticker
          are left defined but intentionally never rendered.) */}
      {scene.subscribe_chip && <SubscribeChip durationFrames={durationFrames} />}
      {scene.credit && <Credit text={scene.credit} top={creditTop} />}
    </AbsoluteFill>
  );
};

// Small "SUBSCRIBE" pill that pops on the CLIMAX beat for ~2s (no dedicated subscribe scene —
// that converted ~0% and leaked). Centered low, clear of the lower-RIGHT action rail and the
// lower-middle scoreboard; a subject-tied subscribe line is voiced over this same beat.
const SubscribeChip: React.FC<{ durationFrames: number }> = ({ durationFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const inS = spring({ frame, fps, config: { damping: 14, stiffness: 160 } });
  const scale = interpolate(inS, [0, 1], [0.5, 1]);
  const holdEnd = Math.min(Math.round(fps * 2.2), durationFrames - 6);
  const op = interpolate(frame, [0, 4, holdEnd, holdEnd + 8], [0, 1, 1, 0], { extrapolateRight: "clamp" });
  const pulse = 1 + 0.04 * Math.sin(frame / 4);
  return (
    <div style={{
      position: "absolute", left: 0, right: 0, bottom: 300,
      display: "flex", justifyContent: "center", opacity: op,
    }}>
      <div style={{
        transform: `scale(${scale * pulse})`, display: "flex", alignItems: "center", gap: 14,
        padding: "16px 32px", borderRadius: 999, background: GOLD,
        boxShadow: "0 8px 30px rgba(0,0,0,0.55)", border: "2px solid rgba(255,255,255,0.85)",
      }}>
        <div style={{
          width: 0, height: 0, borderTop: "13px solid transparent",
          borderBottom: "13px solid transparent", borderLeft: "20px solid #111",
        }} />
        <span style={{
          fontFamily: FONT, fontWeight: 800, fontSize: 46, letterSpacing: 2,
          color: "#111", textTransform: "uppercase",
        }}>Subscribe</span>
      </div>
    </div>
  );
};

// Drawn gold down-arrow (replaces the 👇 emoji, which boxes in headless Chrome).
const DownArrow: React.FC = () => (
  <div style={{
    width: 0, height: 0, margin: "22px auto 0",
    borderLeft: "26px solid transparent", borderRight: "26px solid transparent",
    borderTop: "34px solid #E7B23C", filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.5))",
  }} />
);

const EndCard: React.FC<{
  q: string; handle: string; outro?: { audioFile: string; seconds: number };
  bg?: { bgVideo?: string; credit?: string }; creditTop?: number; topPad?: number;
}> = ({ q, handle, outro, bg, creditTop, topPad }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 16 } });
  const pop = interpolate(s, [0, 1], [0.8, 1]);
  const hasBg = !!bg?.bgVideo;
  return (
    <AbsoluteFill>
      {bg?.bgVideo ? <VideoBg src={bg.bgVideo} /> : null}
      {hasBg ? <DarkOverlay /> : null}
      <AbsoluteFill style={{
        background: hasBg ? "transparent" : "radial-gradient(120% 90% at 50% 40%,#1C1C1E,#0A0A0B)",
        // When a scoreboard/badge sits ~1/3 down, push the centred content below it (topPad)
        // so the comment-bait text never overlaps the board.
        alignItems: "center", justifyContent: "center", textAlign: "center",
        paddingTop: topPad ?? SAFE_TOP, paddingBottom: SAFE_BOTTOM, paddingLeft: PAD_L, paddingRight: PAD_R,
        fontFamily: "'Arial Narrow','Helvetica Neue',Arial,sans-serif", transform: `scale(${pop})`,
      }}>
        {outro && <Audio src={staticFile(outro.audioFile)} />}
        <div style={{
          fontWeight: 800, fontSize: 78, lineHeight: 1.15, color: "#fff", maxWidth: SAFE_W,
          textShadow: hasBg ? "0 4px 30px rgba(0,0,0,0.9)" : "none",
        }}>{q}</div>
        <DownArrow />
        <div style={{
          marginTop: 48, fontWeight: 800, letterSpacing: 6, fontSize: 40,
          textTransform: "uppercase", textShadow: hasBg ? "0 3px 16px rgba(0,0,0,0.9)" : "none", ...goldText,
        }}>{handle}</div>
      </AbsoluteFill>
      {bg?.credit ? <Credit text={bg.credit} top={creditTop} /> : null}
    </AbsoluteFill>
  );
};

export const TikiTakaVideo: React.FC<Props> = ({ scenes, comment_bait, handle, outro, endCard, matchup }) => {
  const hasMatchup = !!(matchup && matchup.length === 2);
  const hasScoreboard = hasMatchup && scenes.some((s) => /\d+\s*[-–]\s*\d+/.test(String(s.score || "")));
  const hasMatchupBadge = hasMatchup && !hasScoreboard;  // flag-VS preview badge (no running score)
  const creditTop = 196;  // always rides just under the watermark; the scoreboard now sits centered in the lower-middle
  let from = 0;
  // Running-scoreboard timeline: one entry per scene at its cumulative start frame, carrying the
  // score in force at that beat (empty `score` inherits the previous beat; defaults to 0-0).
  const scoreTimeline: ScoreEntry[] = [];
  const scoreboardHidden: { from: number; to: number }[] = [];  // group-table beats — no scoreboard
  let curHome = 0, curAway = 0;
  const seqs = scenes.map((scene, i) => {
    const dur = framesFor(scene.seconds);
    if (scene.score) {
      const m = String(scene.score).split(/[-–]/).map((x) => parseInt(x.trim(), 10));
      if (m.length === 2 && Number.isFinite(m[0]) && Number.isFinite(m[1])) { curHome = m[0]; curAway = m[1]; }
    }
    scoreTimeline.push({ fromFrame: from, home: curHome, away: curAway });
    if (scene.group_table?.length) scoreboardHidden.push({ from, to: from + dur });
    const seq = (
      <Sequence key={i} from={from} durationInFrames={dur}>
        <Card scene={scene} durationFrames={dur} dir={i % 2 === 0 ? 1 : -1} index={i} creditTop={creditTop} hasScoreboard={hasScoreboard} hasMatchupBadge={hasMatchupBadge} />
        <Audio src={staticFile(scene.audioFile)} />
      </Sequence>
    );
    from += dur;
    return seq;
  });
  const contentFrames = from;
  const endFrames = outro ? framesFor(outro.seconds + 1) : framesFor(4);
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {seqs}
      <Sequence from={contentFrames} durationInFrames={endFrames}>
        <EndCard q={comment_bait} handle={handle || "@tikitakafootytv"} outro={outro} bg={endCard} creditTop={creditTop} />
      </Sequence>
      {/* Persistent head-to-head element, centered in the lower-middle. Both the running SCOREBOARD
          (recaps) and the flag-VS badge (previews) span the CONTENT scenes only — hidden on the
          comment-bait end card; the scoreboard is further hidden on any group-table beat. */}
      {hasMatchup && (hasScoreboard
        ? (
          <Sequence from={0} durationInFrames={contentFrames}>
            <Scoreboard pair={matchup!} timeline={scoreTimeline} hidden={scoreboardHidden} />
          </Sequence>
        ) : (
          <Sequence from={0} durationInFrames={contentFrames}>
            <MatchupBadge pair={matchup!} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};
