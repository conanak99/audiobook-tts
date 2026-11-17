# Voice onboarding

Use audio you have permission to use. The registry lives in `references/voices/<id>/voice.json`; retain references, transcripts, STT evidence, and auditions together.

## Workflow

```sh
python3 -m viettts voice candidates "/path/audio-or-video.mp4" --id my-voice
python3 -m viettts voice cut my-voice --candidate 1 --candidate 2
python3 -m viettts voice transcribe my-voice
python3 -m viettts voice set-transcript my-voice --ref 1 --file /path/ref1.txt
python3 -m viettts voice set-transcript my-voice --ref 2 --file /path/ref2.txt
python3 -m viettts voice samples my-voice
python3 -m viettts voice approve my-voice --gender female --style "warm" --fits "narration"
python3 -m viettts voice list
```

1. **Candidates:** local media or a URL; for long sources pass `--from` / `--to`. Listen before selecting.
2. **Cut:** prefer two clean 15–20-second clips from one speaker with consistent tone and little silence. The tool fits references into at most 30 seconds total. Cutting again replaces that voice's previous references.
3. **Transcribe:** NanoGPT STT models and independent judges produce drafts and evidence. Requires credentials; sends audio externally.
4. **Review:** preserve exact words, fillers, names, and code-switching. Save every reference's transcript. A draft is not approval.
5. **Samples:** generates three auditions in one Drama-3 model load. Listen for similarity, missing words, noise, and long pauses; inspect retries.
6. **Approve:** only after the listener accepts the samples. Approval updates the generated voice table in the audiobook skill.

Use `voice note <id> "..."` to record performance/fit observations in `voice.json`. Notes are not included in the compact generated table.

Approved ids can be used in a cast (`"female": "<id>"`, or as any role or speaker; see `casts/*.json`) passed with `audiobook build ... --cast`. VieNeu preset names do not need onboarding. `audiobook make-ref --voice "Thiện Minh"` can create a synthetic VieNeu reference for Drama-3; these explicit references are the exception to the approved-id requirement.

After changing Drama-3 weights, regenerate auditions and listen again. Existing approvals and transcripts remain, but stale samples are flagged.

For agent-assisted selection, transcription review, and approval gates, see the [voice-onboarding skill](../.opencode/skills/voice-onboarding/SKILL.md).
