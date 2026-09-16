---
name: image-ocr-vision-provider
description: Use when Agent OS needs governed OCR or visual extraction for image/PDF attachments, especially image bucket max_steps recovery, OCR_RESULT/LAYOUT_RESULT generation, or dry-run gated Qwen-VL style vision provider routing.
---

# Image OCR Vision Provider

## Trigger

Use this skill when the task asks to:

- read text, numbers, tables, colors, or visible objects from an image attachment
- recover `max_steps` failures caused by image/PDF visual evidence
- integrate PaddleOCR, Tesseract, Qwen-VL, or another vision provider
- produce `OCR_RESULT`, `LAYOUT_RESULT`, or `VISION_RESULT`
- route visual extraction through owner-gated shadow/canary mode

## When Not To Use

- Do not use for normal web research without image/PDF visual evidence.
- Do not use for global model routing.
- Do not use to call a paid or external provider without owner approval.
- Do not use to write visual extraction results into trusted memory automatically.

## Runtime Contract

All visual extraction must return one of these schemas.

```text
OCR_RESULT
engine: <paddleocr|tesseract|none>
status: <ok|engine_missing|error>
source_path: <local path>
language: <detected|configured>
text: <recognized text>
blocks:
  - text: <text>
    confidence: <0..1 or unknown>
    bbox: <x1,y1,x2,y2 or unknown>
```

```text
LAYOUT_RESULT
engine: <paddleocr|surya|none>
status: <ok|engine_missing|error>
source_path: <local path>
pages:
  - page: <number>
    text_blocks: <count>
    tables: <count>
    figures: <count>
markdown: <layout-preserving markdown if available>
json: <structured layout if available>
```

```text
VISION_RESULT
provider: <qwen-vl|other>
status: <dry_run|owner_approved_ok|blocked|error>
scope: image_bucket_only
prompt: <visual extraction prompt>
answer_candidates:
  - value: <candidate>
    evidence: <short evidence>
    confidence: <low|medium|high|unknown>
```

Never submit the schema header itself as the final answer.

`IMAGE_META`, `OCR_RESULT`, `LAYOUT_RESULT`, and `VISION_RESULT` are evidence records, not answers. The answer verifier must reject these headers as final answers.

## Dependencies

This skill is dependency-aware, not dependency-installing.

- PaddleOCR is the preferred primary OCR/layout engine when installed.
- Tesseract is the preferred local fallback when installed.
- Qwen-VL style providers are external or local model providers and must stay dry-run unless owner approval exists.
- When no OCR engine exists, return `OCR_RESULT status=engine_missing` and preserve `IMAGE_META` if available.

Example missing-engine response:

```text
OCR_RESULT
engine: none
status: engine_missing
source_path: C:/path/to/image.png
language: unknown
text:
blocks: []
```

## Engine Selection

1. Use PaddleOCR first when installed and enabled.
2. Use Tesseract fallback for local text OCR when PaddleOCR is missing.
3. Use metadata-only `IMAGE_META` when no OCR engine exists.
4. Escalate to `VISION_RESULT` only when:
   - the task is in the image bucket
   - OCR is missing or insufficient
   - provider is configured
   - owner approval is present

## Agent OS Integration

For Agent OS, integrate at the tool boundary:

```text
read_attachment(image/pdf)
  -> modality detector
  -> OCR/layout adapter
  -> OCR_RESULT or LAYOUT_RESULT
  -> verifier
```

Escalation to a vision provider must be separate:

```text
image bucket task
  -> OCR missing or low confidence
  -> VISION_RESULT dry_run
  -> owner approval
  -> provider shadow/canary call
```

The integration must not mutate registry lifecycle, skill trust state, or global model routing.

## Owner Gate

Vision provider calls are blocked unless all conditions are true:

- `vision_provider.enabled = true`
- `vision_provider.mode in ["shadow", "canary"]`
- `owner_approval_id` is present
- `task.modality == "image_attachment"`
- `cost_limit` is set

Default behavior is `dry_run`.

## Checklist

- Identify modality before extraction.
- Prefer local OCR before external vision.
- Return structured evidence, not prose.
- Preserve source path and engine status.
- Reject fake OCR when engine is missing.
- Keep output out of trusted memory unless owner approves.

## Failure Modes

- `engine_missing`: local OCR engine not installed.
- `low_confidence`: OCR text is present but not enough to answer.
- `layout_loss`: OCR text loses table/grid order.
- `provider_blocked`: vision provider would be useful but lacks owner approval.
- `scope_violation`: non-image task attempted to call vision provider.

## Honest Boundary

This skill does not install PaddleOCR, Tesseract, or Qwen-VL by itself. It defines how Agent OS should use them when available. It also does not guarantee score improvement on visual benchmarks without a real OCR or vision engine.

## References

- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- Qwen-VL: https://github.com/QwenLM/Qwen3-VL
