import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Img, staticFile } from "remotion";
import { CountUp } from "./CountUp";

const GOLD = "linear-gradient(180deg,#F7D774,#C8881B)";
const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";
const goldText: React.CSSProperties = {
  backgroundImage: GOLD, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
};

// Parse "MESSI 13 vs MBAPPE 12" or "HAALAND | MBAPPE" -> two {label,val} sides (val optional).
const parseVs = (s: string): null | [{ label: string; val: number | null }, { label: string; val: number | null }] => {
  const parts = (s || "").split(/\s+vs\.?\s+|\s*\|\s*/i);
  if (parts.length !== 2) return null;
  const side = (p: string) => {
    const m = p.trim().match(/^(.*?)[\s:]*(\d{1,4})\s*$/);
    return m && m[1].trim() ? { label: m[1].trim(), val: parseInt(m[2], 10) } : { label: p.trim(), val: null };
  };
  return [side(parts[0]), side(parts[1])];
};

/**
 * Head-to-head comparison: two sides slide in from opposite edges, a "VS" badge clashes in the
 * middle, and (when numbers are present) value count-ups + comparison bars fill. For
 * this_or_that / comparison_split scenes whose on_screen_text reads "A 13 vs B 12".
 * Falls back to the standard stat layout if it can't parse two sides.
 */
export const VsSplit: React.FC<{
  scene: { on_screen_text: string; stat_callout: string; vsImages?: (string | null)[] };
  statFontSize: number; shadow: string;
}> = ({ scene, statFontSize, shadow }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sides = parseVs(scene.on_screen_text);
  const flags = scene.vsImages || [];

  // Graceful fallback: render like the default card so existing comparison scenes don't break.
  if (!sides) {
    return (
      <>
        {scene.stat_callout ? (
          <div style={{
            fontFamily: FONT, fontWeight: 800, fontSize: statFontSize, lineHeight: 0.9,
            letterSpacing: -6, whiteSpace: "nowrap", textShadow: shadow, ...goldText,
          }}>{scene.stat_callout}</div>
        ) : null}
        <div style={{
          marginTop: 24, fontFamily: FONT, fontWeight: 800, fontSize: 84, lineHeight: 1.05,
          letterSpacing: 1, textTransform: "uppercase", color: "#fff", maxWidth: 900, textShadow: shadow,
        }}>{scene.on_screen_text}</div>
      </>
    );
  }

  const [L, R] = sides;
  const sIn = spring({ frame, fps, config: { damping: 16, stiffness: 120 } });
  const lx = interpolate(sIn, [0, 1], [-520, 0]);
  const rx = interpolate(sIn, [0, 1], [520, 0]);
  const op = interpolate(sIn, [0, 0.5], [0, 1], { extrapolateRight: "clamp" });
  const vs = spring({ frame: frame - 6, fps, config: { damping: 7, stiffness: 240 } });
  const vsScale = interpolate(vs, [0, 1], [2.6, 1]);
  const hasVals = L.val != null && R.val != null;
  const maxV = Math.max(L.val || 0, R.val || 0, 1);
  const barP = interpolate(frame, [12, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const Col: React.FC<{ side: { label: string; val: number | null }; x: number; align: "flex-start" | "flex-end"; img?: string | null }> =
    ({ side, x, align, img }) => (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", transform: `translateX(${x}px)`, opacity: op }}>
        {img ? (
          <div style={{
            marginBottom: 18, padding: 7, background: "#fff", borderRadius: 14,
            boxShadow: "0 12px 26px rgba(0,0,0,0.55)",
          }}>
            <Img src={staticFile(img)} style={{ width: 230, height: 153, objectFit: "cover", borderRadius: 8, display: "block" }} />
          </div>
        ) : null}
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 60, color: "#fff", textTransform: "uppercase", textShadow: shadow, textAlign: "center", lineHeight: 1 }}>{side.label}</div>
        {side.val != null ? (
          <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 150, lineHeight: 1, marginTop: 8, textShadow: shadow, ...goldText }}>
            <CountUp to={side.val} />
          </div>
        ) : null}
        {hasVals ? (
          <div style={{ width: "78%", height: 14, marginTop: 14, background: "rgba(255,255,255,0.16)", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ width: `${((side.val || 0) / maxV) * barP * 100}%`, height: "100%", background: GOLD, borderRadius: 8 }} />
          </div>
        ) : null}
      </div>
    );

  return (
    <div style={{ width: "100%", maxWidth: 960, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
      <Col side={L} x={lx} align="flex-end" img={flags[0]} />
      <div style={{
        flex: "0 0 auto", fontFamily: FONT, fontWeight: 800, fontSize: 96, transform: `scale(${vsScale})`,
        ...goldText, textShadow: shadow, padding: "0 6px",
      }}>VS</div>
      <Col side={R} x={rx} align="flex-start" img={flags[1]} />
    </div>
  );
};
