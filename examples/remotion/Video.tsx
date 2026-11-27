import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { Captions } from "./Captions";
// Written by the `captions` tool next to the voice-over. Import it directly: no fetching.
import captions from "../public/audio/voice.captions.json";

const FPS = 30;
export const GENERATED_VIDEO_DURATION = Math.ceil((captions.duration + 0.5) * FPS);

export const GeneratedVideo: React.FC = () => {
  useVideoConfig();
  return (
    <AbsoluteFill style={{ background: "linear-gradient(135deg, #0b1220, #1d3557)" }}>
      <Audio src={staticFile("audio/voice.wav")} />
      <Sequence from={0}>
        <Captions words={captions.words} />
      </Sequence>
    </AbsoluteFill>
  );
};
