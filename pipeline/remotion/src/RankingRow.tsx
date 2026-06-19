import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { fitText } from "@remotion/layout-utils";

const GOLD = "linear-gradient(180deg,#F7D774,#C8881B)";
const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";
const goldText: React.CSSProperties = {
  backgroundImage: GOLD, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
};

// "5. ARGENTINA — the holders" -> { rank:"5", team:"ARGENTINA", tag:"the holders" }
const parseRow = (s: string) => {
  const m = (s || "").match(/^\s*#?(\d{1,2})[.)]\s*(.*)$/);
  const rest = m ? m[2] : s || "";
  const [team, ...t] = rest.split("—");
  return { rank: m ? m[1] : "", team: team.trim(), tag: t.join("—").trim() };
};

/**
 * Ranking countdown reveal: the rank numeral STAMPS in (scale overshoot + rotate), the team
 * label SLIDES in from the right, and a gold underline wipes across. Frame-driven (deterministic).
 * Returns content that flows inside the Card's centered/bottom-anchored container.
 */
export const RankingRow: React.FC<{ scene: { on_screen_text: string }; shadow: string }> = ({ scene, shadow }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { rank, team, tag } = parseRow(scene.on_screen_text);

  const stamp = spring({ frame, fps, config: { damping: 9, stiffness: 200 } });
  const rankScale = interpolate(stamp, [0, 1], [2.1, 1]);
  const rankRot = interpolate(stamp, [0, 1], [-16, 0]);

  const slide = spring({ frame: frame - 4, fps, config: { damping: 18, stiffness: 130 } });
  const labelX = interpolate(slide, [0, 1], [400, 0]);
  const labelOp = interpolate(slide, [0, 1], [0, 1]);
  const wipe = interpolate(frame, [8, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const teamSize = team
    ? Math.min(120, fitText({ text: team, withinWidth: 620, fontFamily: FONT, fontWeight: 800, letterSpacing: "0px" }).fontSize)
    : 0;

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 26, maxWidth: 920 }}>
      <div style={{
        fontFamily: FONT, fontWeight: 800, fontSize: 230, lineHeight: 0.8, flex: "0 0 auto",
        transform: `scale(${rankScale}) rotate(${rankRot}deg)`, transformOrigin: "center",
        textShadow: shadow, ...goldText,
      }}>{rank}</div>
      <div style={{ textAlign: "left", transform: `translateX(${labelX}px)`, opacity: labelOp }}>
        <div style={{
          fontFamily: FONT, fontWeight: 800, fontSize: teamSize, lineHeight: 0.95,
          color: "#fff", textTransform: "uppercase", textShadow: shadow, whiteSpace: "nowrap",
        }}>{team}</div>
        <div style={{ height: 8, marginTop: 12, width: `${wipe * 100}%`, maxWidth: 620, background: GOLD, borderRadius: 4 }} />
        {tag ? (
          <div style={{
            marginTop: 12, fontFamily: FONT, fontWeight: 700, fontSize: 36, letterSpacing: 1,
            color: "#fff", opacity: 0.85, textTransform: "uppercase", textShadow: shadow,
          }}>{tag}</div>
        ) : null}
      </div>
    </div>
  );
};
