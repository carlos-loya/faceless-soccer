import React from "react";
import { Composition } from "remotion";
import { TikiTakaVideo, FPS, framesFor } from "./TikiTakaVideo";

const empty = { topic: "", comment_bait: "", cta: "", handle: "@tikitakafootytv", scenes: [] };

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TikiTaka"
      component={TikiTakaVideo as any}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={300}
      defaultProps={empty as any}
      calculateMetadata={({ props }: any) => {
        const sceneFrames = (props.scenes || []).reduce(
          (a: number, s: any) => a + framesFor(s.seconds),
          0
        );
        const endFrames = props.outro ? framesFor((props.outro.seconds || 3) + 1) : framesFor(4);
        return { durationInFrames: Math.max(sceneFrames + endFrames, 30) };
      }}
    />
  );
};
