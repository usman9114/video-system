# Phase 1: Tool Research (2026-11-26)

## Shortlist
| # | Option | Cost | License | Agent-controllable | Verdict |
|---|---|---|---|---|---|
| 1 | **Remotion + FFmpeg + Whisper (recommended)** | $0 | Remotion Free License (individuals & teams of 3 or fewer, commercial use OK) | Yes. React/TS code + JSON props, official Claude Code Agent Skills (`npx skills add remotion-dev/skills`) | Best for a config-driven reusable template with animated captions, hook text, CTA, B-roll slots |
| 2 | Pure FFmpeg + Python (auto-editor, faster-whisper/WhisperX, ASS subtitles) | $0 | LGPL/GPL, MIT, BSD | Yes. CLI scripts | Simplest and fastest. Text and caption animation is fiddly. Kept as the cutting/audio layer and as the fallback |
| 3 | Kinocut (formerly mcp-video) MCP server | $0 | Apache-2.0 | Yes. MCP tools in Claude Code | Real and local, but a young project with fast-changing versions. It wraps FFmpeg, which Claude Code can already run directly, so the extra layer adds little |

## Rejected
- OpenReel Video (MIT, browser-based): real and free, but it's a GUI editor with no scripting or agent API. Its README also promotes a crypto token.
- FFmpeg Micro MCP: processes video in the cloud with metered usage. Not local and not $0.
- video-dev/ffmpeg-mcp-comp: its README says "exploration only, not for production".
- CapCut/Descript/hosted AI editors: closed, with paid tiers and watermarks. Not automatable.

## Supporting tools
- Silence/pause removal: auto-editor (WyattBlue). Cutting from Whisper word timestamps is more precise.
- Captions: faster-whisper / WhisperX (local, word timestamps, CPU OK for short clips).
- Audio cleanup: FFmpeg `loudnorm` + `afftdn` (built in). DeepFilterNet (MIT/Apache) if noise is bad.
- B-roll: Pixabay (free commercial use, API free). Pexels (free; new API key issuance reported paused, so download manually).
- Music: Pixabay Music (free commercial use; check each track). For talking-head sales videos, often no music at all.
- Lip-sync (Phase 6): MuseTalk (MIT code; weights tagged OpenRAIL-M; about 4 GB VRAM GPU) and LatentSync (OpenRAIL weights; about 18 GB VRAM). Not the default.

## Caveats
- Verified from official docs and repos, not yet by installing. A smoke test in Phase 2 confirms that each tool actually works.
- Remotion says its license "will slightly change" in v5.0. Pin v4.x.
