# v0.9 桌面界面设计验收

## 对比目标

- Source visual truth: `C:\Users\27198\.codex\generated_images\01a08ac2-9b59-7df3-b250-19c16b65f925\exec-6da1ea38-137e-4aca-a775-841145117422.png`
- Implementation screenshot: `C:\Users\27198\.codex\visualizations\2026\09\10\01a08ac2-9b59-7df3-b250-19c16b65f925\implementation-v0.9-qa3.png`
- Combined comparison: `C:\Users\27198\.codex\visualizations\2026\09\10\01a08ac2-9b59-7df3-b250-19c16b65f925\design-comparison-final.png`
- Viewport: Tk client area 1180 × 840 CSS-equivalent pixels on Windows, normal desktop state.
- Pixel normalization: source 1488 × 1058 was resized to 1180 × 840; the implementation window screenshot was 1196 × 879 and its 1180 × 840 client area was cropped before comparison. Density factor was treated as 1 after normalization.
- State: “小星星（第一段）” selected, playback ready, safe preview selected, administrator permission unavailable in the captured process.

## Full-view comparison evidence

The 2360 × 840 combined comparison was opened and inspected at original resolution. The implementation preserves the selected design's dark navy surface system, mint primary action, red stop action, narrow song-library sidebar, centered selected-song hierarchy, progress and current-event area, three playback controls, input-mode card, hotkey card, and bottom status strip. The requested “导入和使用教程” action is visible beside “导入曲谱” without clipping.

The source mock's harmonica icon is intentionally omitted because the user explicitly requested that the element not be added. Native Tk controls replace the mock's decorative icons rather than using emoji or character approximations. Configurable hotkey fields are retained because they are existing product functionality.

## Focused region evidence

A separate crop was not required: the import grid, song rows, playback controls, mode choices, hotkey fields, and status copy are readable in the original-resolution combined comparison. The tutorial window was also opened directly during verification and reported an actual client size of 660 × 590; its four instruction sections and close action fit within that layout.

## Required fidelity surfaces

- Fonts and typography: Microsoft YaHei UI is used for Chinese UI text. The title, selected song, current event, section headings, metadata, and status text have distinct weights and sizes; no critical text wraps or truncates at 1180 × 840.
- Spacing and layout rhythm: the sidebar and main stage retain the mock's two-column composition. The tutorial button is aligned with the import button, while MIDI import and refresh form a balanced second row.
- Colors and visual tokens: dark background, elevated navy surfaces, mint accent, muted blue-gray text, warning amber, and semantic red stop state remain consistent and readable.
- Image quality and asset fidelity: no raster assets are required in the final implementation. The mock's logo omission is an explicit user decision; no placeholder, emoji, text glyph, or handmade approximation was substituted.
- Copy and content: product wording is factual and specific to the in-game harmonica. Emotional marketing copy was removed. Hotkey labels and tutorial instructions use F8 start, F9 stop, and F10 pause/resume as defaults while the UI still displays the user's saved custom bindings.

## Comparison history

1. Initial implementation review found a P1 hierarchy mismatch because the selected-song title was too small, plus P2 mismatches for the missing current-event block, oversized visible log, reversed lower-card order, and a low-emphasis stop action.
2. The font configuration was corrected so named Tk styles control their sizes; a current-event block was added; the log was reduced to a status strip; input mode and hotkey cards were reordered; and the stop action received the semantic red treatment.
3. The second full-view comparison confirmed that those P1/P2 issues were resolved. Remaining native-widget differences are expected constraints rather than actionable fidelity defects.

## Findings

No actionable P0, P1, or P2 findings remain.

## Implementation checklist

- [x] Keep all existing import, playback, mode, settings, and hotkey behavior working.
- [x] Add the side-by-side “导入和使用教程” action.
- [x] Open a readable tutorial window with import and playback guidance.
- [x] Remove sentimental copy and use game-specific factual wording.
- [x] Verify the final main window at 1180 × 840.
- [x] Run the complete automated test suite.

## Follow-up polish

- P3: a future packaged release can add a professionally supplied application icon if the user later wants one.

final result: passed

