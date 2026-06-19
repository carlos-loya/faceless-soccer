import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Img, staticFile } from "remotion";

const GOLD = "linear-gradient(180deg,#F7D774,#C8881B)";
const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";
const goldText: React.CSSProperties = {
  backgroundImage: GOLD, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
};

// "TSHABALALA vs MARQUEZ" -> ["TSHABALALA","MARQUEZ"] (drop any trailing number).
const parseTwo = (s: string): [string, string] | null => {
  const parts = (s || "").split(/\s+vs\.?\s+|\s*\|\s*/i);
  if (parts.length !== 2) return null;
  return [parts[0].trim().replace(/[\s:]*\d{1,4}\s*$/, ""), parts[1].trim().replace(/[\s:]*\d{1,4}\s*$/, "")];
};

// Generic head-and-shoulders silhouette for a scorer with no free photo (copyright-safe placeholder).
const Silhouette: React.FC = () => (
  <svg viewBox="0 0 100 120" width="100%" height="100%" style={{ display: "block" }}>
    <rect width="100" height="120" fill="#2A2A2E" />
    <circle cx="50" cy="44" r="22" fill="#6B6B72" />
    <path d="M12 120 C12 86 32 72 50 72 C68 72 88 86 88 120 Z" fill="#6B6B72" />
  </svg>
);

// iPhone-sticker white outline (matches the corner subject cutout look).
const WHITE_OUTLINE =
  "drop-shadow(3px 0 0 #fff) drop-shadow(-3px 0 0 #fff) drop-shadow(0 3px 0 #fff) " +
  "drop-shadow(0 -3px 0 #fff) drop-shadow(0 12px 18px rgba(0,0,0,0.55))";

/**
 * Head-to-head SCORERS layout: two players slide in from opposite edges and the final score
 * (scene.stat_callout, e.g. "2-0") clashes in the middle. Each side renders, in priority order:
 * a background-removed CUTOUT (scene.vsCutouts[i] — floating, white-outlined sticker), else a
 * photo chip (scene.vsImages[i]), else a silhouette. For `scorers_split` scenes whose
 * on_screen_text reads "A vs B".
 */
export const ScorersSplit: React.FC<{
  scene: { on_screen_text: string; stat_callout: string; vsImages?: (string | null)[]; vsCutouts?: (string | null)[] };
  shadow: string;
}> = ({ scene, shadow }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const names = parseTwo(scene.on_screen_text);
  const imgs = scene.vsImages || [];
  const cuts = scene.vsCutouts || [];
  const score = (scene.stat_callout || "").trim();

  const sIn = spring({ frame, fps, config: { damping: 16, stiffness: 120 } });
  const lx = interpolate(sIn, [0, 1], [-520, 0]);
  const rx = interpolate(sIn, [0, 1], [520, 0]);
  const op = interpolate(sIn, [0, 0.5], [0, 1], { extrapolateRight: "clamp" });
  const clash = spring({ frame: frame - 6, fps, config: { damping: 7, stiffness: 240 } });
  const scoreScale = interpolate(clash, [0, 1], [2.4, 1]);

  const Col: React.FC<{ label: string; img?: string | null; cut?: string | null; x: number }> = ({ label, img, cut, x }) => (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", transform: `translateX(${x}px)`, opacity: op }}>
      {/* Fixed-height media row, bottom-aligned so heads/feet line up across both columns. */}
      <div style={{ height: 300, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
        {cut ? (
          <Img src={staticFile(cut)} style={{ height: 296, width: "auto", maxWidth: 240, objectFit: "contain", filter: WHITE_OUTLINE }} />
        ) : (
          <div style={{
            width: 220, height: 268, padding: 7, background: "#fff", borderRadius: 18,
            boxShadow: "0 14px 30px rgba(0,0,0,0.6)", overflow: "hidden",
          }}>
            <div style={{ width: "100%", height: "100%", borderRadius: 12, overflow: "hidden" }}>
              {img ? (
                <Img src={staticFile(img)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top center" }} />
              ) : (
                <Silhouette />
              )}
            </div>
          </div>
        )}
      </div>
      <div style={{
        marginTop: 16, fontFamily: FONT, fontWeight: 800, fontSize: 52, color: "#fff",
        textTransform: "uppercase", textShadow: shadow, textAlign: "center", lineHeight: 1,
      }}>{label}</div>
    </div>
  );

  if (!names) {
    return <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 84, ...goldText, textShadow: shadow }}>{score || scene.on_screen_text}</div>;
  }

  return (
    <div style={{ width: "100%", maxWidth: 900, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
      <Col label={names[0]} img={imgs[0]} cut={cuts[0]} x={lx} />
      {score ? (
        <div style={{
          flex: "0 0 auto", fontFamily: FONT, fontWeight: 800, fontSize: 104, lineHeight: 1,
          transform: `scale(${scoreScale})`, ...goldText, textShadow: shadow, padding: "0 4px", whiteSpace: "nowrap",
        }}>{score}</div>
      ) : null}
      <Col label={names[1]} img={imgs[1]} cut={cuts[1]} x={rx} />
    </div>
  );
};
