Plan for the new “Media Review” page
Purpose: Upload a VTT + DOCX + video/audio and review a synchronized transcript with click-to-seek playback, like the audio transcription flow but without server-side transcription/processing.

Preparation
- [x] Review existing transcribe components, store, and patterns to reuse
- [x] Draft plan with milestones and acceptance criteria
- [x] Convert plan to actionable checklist with tracking boxes
- [x] Finalize sequence to build top-to-bottom
Scope and milestones
- [ ] Milestone 1 — Frontend-only MVP
- [ ] New route /media with:
- [ ] Multi-file drag-and-drop for .vtt and video/* or audio/* (DOCX dropped).
- [ ] Video/audio player with play/pause, seek, speed, and volume.
- [ ] Transcript pane parsed from VTT; clicking a segment seeks playback; active segment auto-highlights as media plays.
- [ ] Add a “New Page” button to the header of Transcribe that links to /media.
- [ ] No backend changes; files are processed in-browser via Blob URLs.
- [ ] Milestone 2 — UX polish
- [ ] Sticky player (like current AudioPlayer) so controls always visible.
- [ ] Auto-scroll to current segment, search/filter in transcript.
- [ ] “Use samples” helper that instructs the user to drag files from new_enhancement/ for quick testing.
- [ ] Milestone 3 — Persistence (optional)
- [ ] Backend endpoint to upload/save assets and store parsed cues.
- [ ] History page support to reopen past media sessions.

Build order (Milestone 1)
- [x] Create route scaffold at src/app/media/page.tsx
- [x] Add “New Page” button link from /transcribe to /media
- [x] Create store src/lib/stores/useMediaReviewStore.ts (URLs, cues, docx text, seek/currentTime)
- [x] Add VTT parsing util at src/lib/utils/vtt.ts
- [ ] Add DOCX parsing via dependency (mammoth) and simple helper util — dropped
- [x] Implement MediaUpload to accept .vtt and video/audio and populate store
- [x] Implement VideoPlayer based on AudioPlayer patterns, wired to store
- [x] Implement TranscriptViewer rendering cues; click-to-seek and active highlighting
- [x] Wire components together on /media page and basic instructions
- [x] Test end-to-end locally with samples in new_enhancement/
- [x] Prevent empty src warning by conditionally rendering player
UI/UX design
/transcribe
- [x] Add a third header button: “New Page” → /media.
/media
- [x] Top: MediaUpload accepts multiple files, validates types (VTT + media), shows which files are loaded.
- [x] Left/main: VideoPlayer (HTMLVideoElement) if video present; otherwise Audio fallback.
- [x] Right/side: TranscriptViewer showing segments from VTT; clicking seeks; current segment highlighted.

Dependencies
- [x] Decide: tiny custom VTT parser (in utils) vs library; proceed with custom util for MVP
State management
- [x] New store useMediaReviewStore (Zustand) in src/lib/stores/:
videoUrl: string, audioUrl: string
vttCues: { start: number; end: number; text: string; speaker?: string }[]
seekToTime: number | null, currentTime: number, isPlaying: boolean
- [x] Setters: setVideoUrl(), setAudioUrl(), setVttCues(), setSeekToTime(), setCurrentTime(), reset()
Components to add
- [x] src/components/media/MediaUpload.tsx
- [x] Drag-and-drop + file input for multiple files
- [x] Accept: .vtt,video/*,audio/*
- [x] Emits parsed outputs:
- [x] Creates object URLs for media
- [x] Parses VTT in-browser
- [x] src/components/media/VideoPlayer.tsx
- [x] Based on AudioPlayer patterns but for <video>
- [x] Reads seekToTime from store; updates currentTime; keeps controls consistent with existing look/feel
- [x] src/components/media/TranscriptViewer.tsx
- [x] Renders segments from vttCues
- [x] Click-to-seek using setSeekToTime(start)
- [x] Auto-highlight and auto-scroll the active segment
- [x] src/lib/utils/vtt.ts
- [x] Minimal VTT parser: extract start/end/text, try to detect speaker tags like [SPEAKER] if present
Routing and wiring
- [x] Create src/app/media/page.tsx
- [x] Layout: MediaUpload on top; VideoPlayer and TranscriptViewer below
- [x] Show instructions for using the sample files in new_enhancement/
- [x] Edit src/app/transcribe/page.tsx
- [x] Add a “New Page” button next to “View History” and “Dashboard” that links to /media
Notes on samples
For MVP testing, drag files from new_enhancement/ directly into the browser; no need to move them to public/.
The provided sample video and VTT may not align perfectly; still sufficient to validate the click-to-seek and highlighting logic.
Risks and considerations
Speaker detection: Only feasible if VTT embeds speaker tags; otherwise we display text without speaker attribution.
Cross-origin: For remote media URLs, ensure CORS and Range support if later loading from backend/cloud.
Performance/UI: Throttle timeupdate syncing to reduce re-renders; handle large VTTs gracefully.
Accessibility: Ensure keyboard controls and ARIA labels on custom controls.
Acceptance criteria
- [ ] Upload VTT + video via drag-and-drop; transcript renders as segments.
- [ ] Playback highlights the current segment; clicking a segment seeks.
- [ ] Button on Transcribe navigates to /media.
Summary:
Reviewed your goal and existing transcribe components/state.
Proposed a small, clear MVP with a new /media route, multi-file upload, video player, and VTT-synced transcript.
Detailed files to add and edits to make, plus future steps for persistence and polish.