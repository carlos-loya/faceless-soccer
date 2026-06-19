import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

/**
 * Odometer-style number reveal: rolls from `from` (default 0) up to `to`, decelerating to
 * land on the final number in `durationFrames` (default ~0.9s). It's a pure function of the
 * current frame, so it renders deterministically in Remotion (no wall-clock animation).
 *
 * Renders just the text (a number with optional prefix/suffix) — color, font, and any scale
 * "pop" are inherited from the parent element, so it drops into the existing stat callout.
 */
export const CountUp: React.FC<{
  to: number;
  from?: number;
  prefix?: string;
  suffix?: string;
  durationFrames?: number;
}> = ({ to, from = 0, prefix = "", suffix = "", durationFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const dur = durationFrames ?? Math.round(fps * 1.1);
  const t = interpolate(frame, [0, Math.max(1, dur)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const value = Math.round(from + (to - from) * t);
  return (
    <>
      {prefix}
      {value.toLocaleString()}
      {suffix}
    </>
  );
};

/**
 * Decide whether a stat_callout string should animate as a CountUp.
 * Countable = a 1–4 digit integer with at most a tiny prefix/suffix (e.g. "16", "5?", "+12").
 * Years (1900–2099) and 0 are left static so they don't oddly roll up from zero.
 */
export const parseCount = (
  s: string
): { to: number; prefix: string; suffix: string } | null => {
  const m = s.match(/^([^\d]{0,2})(\d{1,4})([^\d]{0,2})$/);
  if (!m) return null;
  const n = parseInt(m[2], 10);
  if (n === 0 || (n >= 1900 && n <= 2099)) return null;
  return { to: n, prefix: m[1], suffix: m[3] };
};
