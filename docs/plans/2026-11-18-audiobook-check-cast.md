# Audiobook Check Cast Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `python3 -m viettts audiobook check` validate an adjacent or explicitly selected cast before synthesis, while preserving the no-cast review workflow.

**Architecture:** Add a side-effect-free validation helper beside the existing build-time cast helpers in `viettts/audiobook/build.py`. The check command selects `--cast` first, otherwise a sibling `cast.json`, and asks the helper to load voices and exercise the same speaker resolution used by `plan_units`; validation converts build-planning `SystemExit` failures into printable findings and never initializes a TTS engine.

**Tech Stack:** Python 3.11, `argparse`, `unittest`, existing audiobook script/build helpers.

---

### Task 1: Specify cast discovery and successful validation

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `viettts/audiobook/build.py`
- Modify: `viettts/audiobook/review.py`
- Modify: `viettts/audiobook/build.py:1111-1113`

**Step 1: Write the failing command tests**

Add a temporary-book helper and tests which:

```python
def write_book(self, directory, cast=None):
    script = directory / 'script.txt'
    script.write_text(
        '@title T\n'
        '@speaker ta male narrator\n'
        '@speaker Khả Khả female\n'
        '## C\n'
        '[Khả Khả] Xin chào.\n',
        encoding='utf-8',
    )
    if cast is not None:
        (directory / 'cast.json').write_text(json.dumps(cast, ensure_ascii=False), encoding='utf-8')
    return script
```

- confirm sibling `cast.json` is discovered and reported;
- confirm `--cast PATH` takes precedence over a bad sibling cast;
- confirm an explicit named-speaker voice such as `Khả Khả: lynasa` validates;
- confirm no adjacent or explicit cast skips cast validation and still exits successfully.

**Step 2: Run the focused tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_cli.PackageTests.test_check_discovers_adjacent_cast \
  tests.test_cli.PackageTests.test_check_explicit_cast_overrides_adjacent \
  tests.test_cli.PackageTests.test_check_accepts_named_speaker_voice \
  tests.test_cli.PackageTests.test_check_without_cast_skips_cast_validation -v
```

Expected: FAIL because `check` has no `--cast` option and does not inspect sibling casts.

**Step 3: Add the minimal successful validation path**

In `viettts/audiobook/build.py`, add:

```python
def validate_cast(script, cast_path):
    """Load a cast and exercise build-time speaker/voice resolution without synthesizing."""
    preset, voices = load_cast(argparse.Namespace(cast=cast_path))
    plan_units(script, voices, 'fail')
    return preset, voices, []
```

In `viettts/audiobook/review.py`, resolve the script path, choose:

```python
cast_path = args.cast or script_path.with_name('cast.json')
cast_path = cast_path if cast_path.is_file() else None
```

When `cast_path` exists, call `validate_cast`, print a concise cast summary, and include its findings in the command’s final buildability decision. When it does not exist, preserve existing behavior.

Add `--cast` with `type=Path` to the `check` parser in `viettts/audiobook/build.py`.

**Step 4: Run the focused tests and verify they pass**

Run the command from Step 2.

Expected: PASS.

### Task 2: Reject invalid and incomplete casts

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `viettts/audiobook/build.py`
- Modify: `viettts/audiobook/review.py`

**Step 1: Write failing command tests**

Add tests asserting exit status 1 and useful output for:

```python
{'voices': {'Khả Khả': 'Not A Voice'}}
{'voices': {'Kha Kha': 'lynasa'}}
```

Also add a script speaker with no cast mapping and no known gender, and assert that the cast report identifies the unresolved speaker-to-voice mapping.

**Step 2: Run the focused tests and verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_cli.PackageTests.test_check_rejects_unknown_cast_voice \
  tests.test_cli.PackageTests.test_check_rejects_unmatched_cast_key \
  tests.test_cli.PackageTests.test_check_rejects_unresolved_speaker_voice -v
```

Expected: FAIL because cast exceptions are not yet normalized into check findings and unmatched keys are not fatal.

**Step 3: Complete reusable validation**

Update `validate_cast` to:

- catch `SystemExit` from `load_cast` and `plan_units`;
- return the error text as cast findings rather than terminating before `cmd_check` prints its normal summary;
- turn every `unmatched_cast_keys(voices, script)` result into a finding;
- stop planning after load errors, since no resolved voice map exists.

Update `cmd_check` to print each cast finding with a `cast:` prefix and exit 1 with:

```text
Not buildable yet: fix the cast errors above.
```

**Step 4: Run the focused tests and verify they pass**

Run the command from Step 2.

Expected: PASS.

**Step 5: Commit the implementation**

```bash
git add docs/plans/2026-11-18-audiobook-check-cast.md tests/test_cli.py viettts/audiobook/build.py viettts/audiobook/review.py
git commit -m "Validate audiobook casts during check"
```

### Task 3: Verify regressions and the prepared Ma Hoa casts

**Files:**
- Verify: `tests/test_audiobook.py`
- Verify: `tests/test_cli.py`
- Verify: `outputs/audiobooks/ma-hoa-cach-chung-ta-dung-lai-dan-cac/script.txt`
- Verify: `outputs/audiobooks/ma-hoa-chuyen-van-du-hi-dao-cua-hop-hoan-tong/script.txt`

**Step 1: Run targeted audiobook and CLI tests**

Run:

```bash
python3 -m unittest tests.test_audiobook tests.test_cli -v
```

Expected: PASS.

**Step 2: Run static checks**

Run:

```bash
uv run ruff check viettts tests
uv run mypy
```

Expected: PASS.

**Step 3: Check both prepared volumes without synthesis**

Run:

```bash
python3 -m viettts audiobook check outputs/audiobooks/ma-hoa-cach-chung-ta-dung-lai-dan-cac/script.txt
python3 -m viettts audiobook check outputs/audiobooks/ma-hoa-chuyen-van-du-hi-dao-cua-hop-hoan-tong/script.txt
```

Expected: both commands discover their adjacent `cast.json`, report successful cast validation, preserve the reviewed advisory findings, and exit 0. Do not run `audiobook build`, a worker, or any synthesis command.

**Step 4: Confirm no audio artifacts were created**

Run:

```bash
find \
  outputs/audiobooks/ma-hoa-cach-chung-ta-dung-lai-dan-cac \
  outputs/audiobooks/ma-hoa-chuyen-van-du-hi-dao-cua-hop-hoan-tong \
  -type f \( -name '*.wav' -o -name '*.m4b' \) -print
```

Expected: no output.
