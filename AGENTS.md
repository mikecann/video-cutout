# Agent guidance, video-cutout

This is a Windows Python CLI for talking-head video background removal. Source
files live at the repo root. `install.ps1` writes launchers to `C:\dev\tools`
and registers this tool under the shared Explorer "Mike's Tools" submenu.

## Working here

- Keep source in this clone. `C:\dev\tools` gets generated launchers and large
  binaries, never copies of the source. Do not commit `.exe`, `.dll` or models.
- Use test-first development for non-trivial changes. Update affected test
  expectations with behaviour changes and rerun the relevant tests.
- Test before committing. Run `python -m unittest discover -s tests -v` after
  installing `requirements-test.txt`. Check `python video_cutout.py --help`.
- Parse every `.ps1` with PowerShell's
  `[System.Management.Automation.Language.Parser]::ParseFile`. On Windows, run
  `powershell -ExecutionPolicy Bypass -File tests\test_install.ps1`, then smoke-test
  `video-cutout` from a terminal and Explorer with a short real video. Check exit
  codes. Syntax checks on macOS do not verify registry, batch or CUDA behaviour.
- Keep `.bat` files ASCII. Use `-Encoding ASCII` when writing generated stubs.
- Accept `EXEDIR` for large binaries and fall back to the launcher's directory.
  FFmpeg may also live in `C:\dev\tools` or on PATH. Do not search repo ancestors.
- Re-run `install.ps1` after changing registered commands or menu entries.
  Source-only changes work immediately because stubs point at this clone.
- Preserve shared Explorer roots and every other tool's verbs. Uninstall must
  remove only `VideoCutout`, its launchers and its generated icon.

## Dependencies and processing

- `deps.ps1` must run directly from this clone and be idempotent. Check Python
  imports before installing, use the repo's `.venv` interpreter for pip, and
  show clear coloured output. Warn about missing manual binaries like FFmpeg
  rather than downloading them. Use `Get-Command` for system dependencies.
- `install.ps1` runs `deps.ps1` unless `-SkipDeps` is supplied. No API keys or
  `.env` are needed; inference is local.
- RVM is the default backend and requires CUDA-enabled PyTorch and an NVIDIA
  GPU. New model downloads go to `C:\dev\tools\_models\video-cutout`; keep the
  previous cache as a read fallback so an existing install keeps its downloads.
- Keep inference imports inside processing functions so tests need only Pillow.
  CI must not download models, install CUDA or require a GPU.
- Preserve full-frame, source-size output by default and ProRes 4444 alpha for
  Resolve. The rembg fallback and its checkerboard preview remain available.
- Keep the backend and codec research in `docs/spike-results.md`.

## Writing

Write plainly and personally. No em dashes or en dashes. PR descriptions start
with `## Why`, explaining what prompted the change and why it is worth making.
