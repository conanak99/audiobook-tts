# Audiobook Check Cast Validation Design

## Goal

Extend `python3 -m viettts audiobook check` so it validates the cast configuration before synthesis.

## Behavior

- Automatically use `cast.json` beside `script.txt` when it exists.
- Accept `--cast PATH` to override the adjacent cast.
- Keep cast validation optional when neither source exists, preserving the speaker-review workflow.
- Reuse the build planner’s existing cast loading and voice resolution.
- Report and fail on:
  - unknown or draft voices;
  - invalid cast engines;
  - cast keys that match neither a role nor a script speaker;
  - script speakers that cannot resolve to a voice.
- Print a short successful cast summary when validation runs.
- Do not initialize or run a TTS engine.

## Implementation

Add a reusable cast-validation helper in `viettts/audiobook/build.py`. `cmd_check` will select the explicit or adjacent cast, invoke the helper, append cast findings to its normal output, and treat cast errors as non-buildable. The CLI parser will expose `--cast`.

## Tests

Add command-level tests covering:

1. automatic adjacent-cast discovery;
2. explicit `--cast` override;
3. valid named speaker voice;
4. unused/misspelled cast key failure;
5. invalid voice failure;
6. no cast remains valid and skips cast validation.
