import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export type Word = { word: string; start: number; end: number };

// Pop-style captions: a few words at a time, the current group springs in.
export const Captions: React.FC<{ words: Word[]; perGroup?: number }> = ({ words, perGroup = 3 }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const t = frame / fps;
  const groups: Word[][] = [];
  for (let i = 0; i < words.length; i += perGroup) groups.push(words.slice(i, i + perGroup));
  const group = groups.find((g, i) => {
    const next = groups[i + 1];
    return t >= g[0].start && (next ? t < next[0].start : t <= g[g.length - 1].end + 0.4);
  });
  if (!group) return null;
  const pop = spring({ frame: frame - Math.round(group[0].start * fps), fps, config: { damping: 12 } });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: height * 0.12 }}>
      <div
        style={{
          fontFamily: "Helvetica, Arial, sans-serif",
          fontWeight: 800,
          fontSize: Math.round(height * 0.07),
          color: "white",
          WebkitTextStroke: `${Math.max(2, Math.round(height * 0.006))}px black`,
          paintOrder: "stroke fill",
          textAlign: "center",
          maxWidth: "85%",
          transform: `scale(${interpolate(pop, [0, 1], [0.8, 1])})`,
        }}
      >
        {group.map((w) => w.word).join(" ")}
      </div>
    </AbsoluteFill>
  );
};
