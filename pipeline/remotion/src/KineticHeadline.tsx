import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";

/**
 * Kinetic headline: the hook text animates in WORD BY WORD (each word springs up + scales in,
 * staggered), so the first second is kinetic instead of a static block. Aimed squarely at the
 * first-second swipe-away. Frame-driven (deterministic). Flows inside the Card container.
 */
export const KineticHeadline: React.FC<{
  text: string;
  shadow: string;
  fontSize?: number;
}> = ({ text, shadow, fontSize = 88 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = (text || "").split(/\s+/).filter(Boolean);
  const stepF = 3; // frames between word entrances

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", justifyContent: "center", alignItems: "baseline",
      columnGap: Math.round(fontSize * 0.3), rowGap: Math.round(fontSize * 0.12),
      maxWidth: 920, textAlign: "center",
    }}>
      {words.map((w, i) => {
        const s = spring({ frame: frame - i * stepF, fps, config: { damping: 12, stiffness: 210 } });
        const op = interpolate(s, [0, 1], [0, 1]);
        const ty = interpolate(s, [0, 1], [30, 0]);
        const sc = interpolate(s, [0, 1], [0.7, 1]);
        return (
          <span key={i} style={{
            display: "inline-block", opacity: op, transform: `translateY(${ty}px) scale(${sc})`,
            fontFamily: FONT, fontWeight: 800, fontSize, lineHeight: 1.04, letterSpacing: 1,
            textTransform: "uppercase", color: "#fff", textShadow: shadow,
          }}>{w}</span>
        );
      })}
    </div>
  );
};
