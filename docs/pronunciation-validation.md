# Pronunciation validation — 2026-10-01

`just qa` passed: Ruff formatting/lint, ty, and **210 Python tests**.
`npm ci`, `npm run build:web`, and `npm run test:web` passed; **70 frontend tests**.
The checked-in Markdown bundle was rebuilt from source. QA and Chromium ran
outside the filesystem sandbox because its asyncio wakeups and browser/esbuild
subprocesses were restricted. No live learner database was modified.

Coverage includes strict Russian/German/Unicode annotation parsing, punctuation,
whole phrases and isolated words, malformed/nested markup, exercise blanks,
clean private grading references, stable persisted IDs, additive migration and
new practice in historical lessons. Mocked API/cache checks cover ownership,
host/origin validation, no synthesis before a click, repeat/restart cache reuse,
in-flight deduplication, four-request concurrency, voice/instruction invalidation,
empty responses, truncated HTTP reads, explicit retry, session deletion and
shutdown. Pronunciation works while the tutor lock is held. Browser/controller
checks cover whole-span controls, Enter/Space, loading/error states, selection,
previous-audio stop, stale-response suppression and retained audio after a browser
playback restriction.

## Live smoke test

A temporary database contained synthetic saved German `Ich lerne.` and Russian
`Я` spans. The real OpenAI speech endpoint produced one MP3 per language using
`gpt-4o-mini-tts`, `marin`, speed 1.0 and locale instructions. Chromium decoded both
clips (1.416 s German and 0.960 s Russian). Provider logs showed **two synthesis
requests total**. Repeat clicks used memory; reloads and a fresh server process
opening the same database showed disk-cache hits without additional synthesis.
Before any click, navigation and rendering made zero pronunciation requests.
No token-cost figure is claimed.

The following single-sample measurements use time from the click event to the
browser media element's `playing` event, on the same local machine. They measure
playback start, not physical speaker output or a network/device benchmark.

| Case | German | Russian |
| --- | ---: | ---: |
| First uncached click, desktop | 2,223 ms | 1,414 ms |
| Browser-memory repeat, desktop | 2 ms | — |
| Disk cache after reload, desktop | 72 ms | 7 ms |
| Disk cache, mobile viewport emulation | 73 ms | 9 ms |
| Browser memory, mobile viewport emulation | 3 ms | 3 ms |
| Disk cache in a fresh server process, desktop | 42 ms | 15 ms |

A later capture run measured cached playback starts between 2 and 83 ms. All
observed cached starts met the one-second target. **Physical desktop/mobile
click-to-audible timing remains unverified**: the environment provides headless
Chromium and mobile viewport emulation, not speaker-output measurement or a
physical mobile device. Mobile autoplay policy is covered by mocked restriction
and retry tests; the timing browser permitted autoplay explicitly.

The live browser also confirmed selectable exact text, stopped audio on lesson
navigation, and no horizontal overflow at 390 px. A simulated delayed 502 response
showed loading and retry states without automatic retry. A new explicit click
then played the already-cached Russian phrase in 10 ms, without synthesis.

## Captures

- [Desktop lesson](screenshots/pronunciation-desktop.png)
- [Mobile lesson](screenshots/pronunciation-mobile.png)
- [Mobile exercise text](screenshots/pronunciation-exercises-mobile.png)
- [Loading state](screenshots/pronunciation-loading-mobile.png)
- [Explicit retry state](screenshots/pronunciation-error-mobile.png)

For physical-device verification, open a new annotated lesson, record first-click
latency separately, then repeat the same phrase, reload, and restart the server.
Measure from the input event to audible output on desktop and a real mobile
browser, including that browser's first-play restriction. Confirm repeated clips
log cache hits without another speech request.

## Fill-in sentence exclusion

Fill-in sentence text is intentionally silent: splitting around a missing word
would produce awkward fragments. New completion contracts reject pronunciation
annotations in the gapped sentence. Separate vocabulary context remains playable.
Historical saved fragment metadata is excluded from public payloads and rejected
by pronunciation lookup, so a stale span ID cannot trigger synthesis. The browser
also ignores stale fragment metadata before and after answer submission. Legacy
fill-in tasks follow the same rule. Regression checks cover generation rejection,
API exclusion, preserved grading references, vocabulary context playback and
rendering after submission.
