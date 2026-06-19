import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { CountUp, parseCount } from "./CountUp";

const GOLD = "linear-gradient(180deg,#F7D774,#C8881B)";
const FONT = "'Arial Narrow','Helvetica Neue',Arial,sans-serif";
const goldText: React.CSSProperties = {
  backgroundImage: GOLD, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
};

// A gold ring that depletes over the scene — the "pause and guess" timer.
const TimerRing: React.FC<{ durationFrames: number }> = ({ durationFrames }) => {
  const frame = useCurrentFrame();
  const R = 74, C = 2 * Math.PI * R;
  const p = interpolate(frame, [0, durationFrames], [0, 1], { extrapolateRight: "clamp" });
  const pulse = 1 + 0.05 * Math.sin(frame / 3);
  return (
    <svg width={190} height={190} style={{ marginTop: 30, transform: `scale(${pulse})` }}>
      <circle cx={95} cy={95} r={R} fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth={11} />
      <circle cx={95} cy={95} r={R} fill="none" stroke="#F7D774" strokeWidth={11} strokeLinecap="round"
        strokeDasharray={C} strokeDashoffset={C * p} transform="rotate(-90 95 95)" />
    </svg>
  );
};

// Green check that stamps in shortly after the answer reveals.
const CheckStamp: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - 10, fps, config: { damping: 8, stiffness: 220 } });
  const sc = interpolate(s, [0, 1], [0, 1]);
  const rot = interpolate(s, [0, 1], [-28, 0]);
  return (
    <div style={{ marginTop: 24, transform: `scale(${sc}) rotate(${rot}deg)` }}>
      <svg width={92} height={92} viewBox="0 0 24 24">
        <path d="M20 6L9 17l-5-5" fill="none" stroke="#39d353" strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
};

/**
 * Quiz reveal: the answer un-blurs and pops in (a satisfying "reveal"), then a green check
 * stamps. On the "guess" beat (stat_callout GUESS/?), shows a depleting timer ring instead.
 * Returns content that flows inside the Card's centered/bottom-anchored container.
 */
export const QuizReveal: React.FC<{
  scene: { on_screen_text: string; stat_callout: string };
  statFontSize: number; shadow: string; durationFrames: number;
}> = ({ scene, statFontSize, shadow, durationFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isGuess = /guess|quiz|\?/i.test(scene.stat_callout || "");

  const rev = spring({ frame, fps, config: { damping: 13, stiffness: 120 } });
  const blur = interpolate(rev, [0, 1], [16, 0]);
  const scale = interpolate(rev, [0, 1], [0.55, 1]);
  const op = interpolate(rev, [0, 0.4], [0, 1], { extrapolateRight: "clamp" });

  return (
    <>
      {scene.stat_callout ? (
        <div style={{
          position: "relative", fontFamily: FONT, fontWeight: 800, fontSize: statFontSize, lineHeight: 0.9,
          letterSpacing: -6, whiteSpace: "nowrap", textShadow: shadow,
          transform: `scale(${isGuess ? 1 : scale})`, filter: isGuess ? "none" : `blur(${blur}px)`,
          opacity: isGuess ? 1 : op, ...goldText,
        }}>{(() => {
          const c = !isGuess && parseCount(scene.stat_callout);
          return c ? <CountUp to={c.to} prefix={c.prefix} suffix={c.suffix} /> : scene.stat_callout;
        })()}</div>
      ) : null}
      <div style={{
        position: "relative", marginTop: 24, fontFamily: FONT, fontWeight: 800, fontSize: 84,
        lineHeight: 1.05, letterSpacing: 1, textTransform: "uppercase", color: "#fff",
        maxWidth: 900, textShadow: shadow,
      }}>{scene.on_screen_text}</div>
      {isGuess ? <TimerRing durationFrames={durationFrames} /> : <CheckStamp />}
    </>
  );
};
