---
name: clapper
description: Make videos with the clapper MCP tools (Remotion and Blender renders, voice-over, captions, stock images, versions with review comments). Use when the user wants a video made, changed, or reviewed.
---

# Clapper: working instructions for the agent

You make videos with the `clapper` MCP tools. Everything happens inside a **project**
(default `default`); all paths are relative to it: code in `src/`, assets in `public/`,
results in `out/`.

## Workflow

1. **Plan before you render.** Agree on length, format (16:9 1920x1080, vertical 1080x1920),
   language and tone. Renders cost minutes; a wrong plan costs more.
2. **Assets first.** `voiceover` -> `captions` (needs the voice-over) -> `stock_image`.
   The tool results contain the exact `staticFile(...)` snippet to use.
3. **Write the scene** with `write_file`.
   - Remotion: `src/Video.tsx` exports `GeneratedVideo` (component) and
     `GENERATED_VIDEO_DURATION` (frames, 30 fps). Derive the duration from the voice-over
     (`captions.duration * 30`), never guess it. Import captions JSON directly
     (`import captions from "../public/audio/voice.captions.json"`); see `examples/remotion/`.
   - Blender: a Python script that builds the scene and renders to `sys.argv[-1]` (the path
     after `--`). Make sure the GPU is really used when there is one: set the Cycles compute
     device and print which device you got; without that Blender silently renders on the CPU.
4. **Render** with `render_remotion` / `render_blender`. They return a job id at once.
   Poll `render_status`; do not wait inside one call. On `error` read `log_tail`, fix the
   cause, and render again. Do not retry unchanged.
5. **Look at the result.** `video_info` for duration, size and audio; `video_frame` at the
   start, the middle and the end, and at every moment you changed. Check for cut-off text,
   overlap, empty placeholders and wrong colours. Never say "done" for something you have
   not looked at.
6. **Version it.** `video_version(file, changes, resolved_comments)` records what you
   changed (seconds, `changed` or `new`, a short text). Only you know what changed, so say it
   precisely.

## Review rounds

When the user has left comments on the timeline: `video_comments` lists the open ones. Make
the next version (`out/video-v2.mp4`, never overwrite v1), then call `video_version` with the
ids you resolved. Say plainly which comments you did **not** resolve and why.

## Rules

- Voice-over and captions need `GROQ_API_KEY`; stock images need `PEXELS_API_KEY` or
  `UNSPLASH_ACCESS_KEY`. If a key is missing the tool says which; tell the user, do not work
  around it. Call `doctor` when something fails to see what this install can do.
- The default voice-over model speaks **English only**. Say so when asked for another
  language instead of delivering English silently.
- Stock photos need credit: put the photographer and page URL from the tool result in the
  video description or an end card.
- Never invent an asset. If an image or logo cannot be fetched, say so and use a plain
  alternative, and mention it.
- Keep every file inside the project. Do not try to read or write elsewhere.
