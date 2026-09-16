---
name: shortdrama-video-generation
description: Plan and prepare AI short-drama video generation workflows. Use when creating short drama, web drama, vertical drama, AI video, shot prompts, character consistency sheets, scene prompts, video-generator selection, production pipeline, continuity QA, or acceptance checks for tools such as Sora, Veo, Runway, Kling, Pika, Luma, Hailuo, or similar video models.
---

# Short Drama Video Generation

Use this skill to turn a story or episode script into a practical AI video production package.

## Workflow

1. Confirm rights and distribution boundary.
   - If the work adapts a known IP, separate internal concept work from commercial release.
   - Require authorization before using protected names, world settings, costumes, logos, music, or existing visual designs.

2. Choose production mode.
   - `text-to-video`: fastest exploration, weakest continuity.
   - `image-to-video`: best for character and costume consistency.
   - `reference-to-video`: use when the tool supports character, style, or scene references.
   - `hybrid`: generate keyframes first, animate per shot, edit externally.

3. Lock continuity before writing prompts.
   - Create one character bible per major role.
   - Create one scene bible per recurring location.
   - Create one visual style bible for lens, color, lighting, aspect ratio, and genre.

4. Convert script to a shot table.
   Required columns:
   - episode
   - scene
   - shot_id
   - duration_seconds
   - character_ids
   - location_id
   - action
   - dialogue_or_voiceover
   - camera
   - lighting
   - generation_prompt
   - negative_prompt
   - continuity_notes
   - selected_tool
   - qa_status

5. Generate in this order.
   - character reference images
   - location reference images
   - 2-4 second motion tests
   - full shot clips
   - voice and subtitles
   - edit assembly
   - continuity repair

6. QA every shot.
   Reject shots with:
   - changed face, age, clothing, weapon, or hairstyle;
   - wrong spatial layout;
   - unreadable emotion;
   - dialogue not matching mouth movement when lip sync is required;
   - camera motion hiding the action;
   - copyright-infringing resemblance to existing actors or adaptations;
   - text artifacts, extra fingers, warped weapons, broken costumes.

## Tool Selection

- Use Sora or Veo-class models for cinematic motion, complex scenes, and natural camera language.
- Use Runway-class tools for creator workflow, shot iteration, video-to-video, and editing controls.
- Use Kling/Hailuo/Pika/Luma-class tools for fast clip iteration, character action tests, and social-video production.
- Use image generation first when character consistency matters more than raw motion quality.
- Use external editing for pacing; do not expect one video model to output a finished 10-minute episode.

## Prompt Pattern

Use this compact structure:

```text
Character: [fixed character bible id and traits]
Scene: [fixed location bible id, time, weather, props]
Action: [one visible action only]
Emotion: [specific physical signs]
Camera: [shot size, movement, lens feel]
Lighting: [source, contrast, color]
Style: [genre and production texture]
Constraints: [no text, no logo, no modern objects, preserve face and costume]
```

For 10-minute drama episodes, split into 80-140 shots. Generate clips at 3-8 seconds, then edit.

## Short Drama Rules

- Start every episode with a visible conflict in the first 10 seconds.
- Put a reveal or reversal every 60-90 seconds.
- End each episode with an unfinished decision, discovery, danger, or emotional rupture.
- Write character detail as visible behavior: hands, breath, gaze, posture, costume damage.
- Write scene detail as usable production data: time, weather, architecture, terrain, props, light source.

## References

Read `references/tool-map.md` when selecting tools or comparing video generators.
Read `references/shot-template.md` when producing shot tables and prompts.

