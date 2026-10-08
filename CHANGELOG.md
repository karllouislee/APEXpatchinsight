# Changelog

This project uses `major.minor.patch` versioning. Every user-visible feature, fix, or behavior change must increment the version and add an entry here.

## [0.9.3] - 2026-09-23

### Fixed
- Reserve main-page top spacing for the fixed Streamlit toolbar.
- Preserve textual exact_values as raw_text without inventing before/after numbers.
- Specify nested numeric-value objects in the patch prompt and remove conflicting root-array instructions.

## [0.9.2] - 2026-09-04

### Added
- **「分析结果报告（确定条目）」export.** A new Markdown download on the export panel: for every change item with at least one determinate direction verdict it writes the official change summary, a plain verdict sentence (普遍支持 / 普遍反对 / 意见分裂), the rates behind it (方向支持率 among decided opinions, 接受率 among all related comments), and up to three reference comments — determinate directions first — as supporting evidence. Items without any determinate direction are listed at the end without a verdict. `core/reporting.analysis_results_markdown` is pure core, same pattern as the existing report exports.

### Changed
- **「未解决率」is gone;「接受率」replaces it** in the results matrix and on the target cards. 未解决率 was derived from 原问题状态, which the review form already stopped treating as comment-derivable; 接受率 (`aggregation.acceptance_rate`) counts 明确支持 comments over all related comments for a target — the share of players the change actually lands with, as opposed to 方向支持率 which only divides decided opinions.

## [0.9.1] - 2026-09-04

### Added
- **Review queue navigation and skip.** The review panel gains 「← 上一条 / 下一条 →」 buttons next to the queue dropdown (form widgets are keyed per comment, so flipping back and forth keeps what you typed), a 「跳过此条（不再提醒）」 button that removes the task from the queue and remembers it in `Project.skipped_reviews`, and a 「恢复已跳过」 button that puts them back. Skip marks survive the queue rebuilds that happen on every stats refresh; 「清空全部分析」 resets them along with the round.

### Changed
- **The review form only asks what a comment text can answer.** 问题类型 / 力度态度 / 原问题状态 are gone from the form — a reviewer cannot reliably pick those from a comment, so the review save no longer overwrites them and the analysis keeps whatever it produced. 改动对象、方向态度、整体立场、信息质量、问题原因、证据引文、疑似反讽 remain.
- A comment whose only queue reason was an undecided 问题类型 no longer enters the review queue (that reason can never be resolved in the form); 「态度无法判断」 still queues.

## [0.9.0] - 2026-09-04

### Added
- **Analysis is a two-stage pipeline.** Stage 1 「话题归类」classifies every comment into a change target (output contract `n/tg/m/q/c`, no attitude) and yields the topic-heat table immediately — you can see which change items are hot before paying for a single attitude verdict. Stage 2 「态度分析」then runs **one target at a time**: the corpus splits into buckets by target, each request carries only that target's change row, and comments stage 1 could not map go to a「未对应到改动」bucket that still gets an attitude ("no matching change" ≠ "no opinion"). Each stage has its own prompt (`comment_topic_prompt.txt` / `comment_attitude_prompt.txt`) and can be run, stopped, and resumed independently.
- **Restart controls on the analysis step:** 「清空全部分析…」(two-step confirm) drops every model-produced result while keeping comments, the human review trail, sampling validations and learned review lessons; 「只重跑态度分析…」keeps the stage-1 topic classification and resets only attitudes — useful when the attitude prompt or review lessons change, since stage 1 does not depend on them.
- The step strip is stage-aware: it shows「已归类」counts for step 3 and「已判定」for step 4, and the analysis step only completes when every valid comment has been judged, not merely classified.

### Changed
- `CommentAnalysis` carries `analysis_stage` (未开始 → 已归类 → 已完成). Rows saved before this split default to 已完成. `overall_stance` / `root_issue_status` / `problem_reason` are only derived for 已完成 rows, so a half-analysed corpus no longer looks like a verdict.
- Stage-2 attitude payloads are small: each request carries one collapsed change row plus one bucket of comments (≈170–240 chars on the reference corpus, vs 4.5k for the old whole-corpus dump).

### Removed
- `prompts/comment_analysis_prompt.txt` — the single-stage prompt is replaced by the two-stage pair.

## [0.8.0] - 2026-09-04

### Fixed
- **The model can judge direction and intensity again.** The previous prompt stated output *style* rules but never listed the fields, so GLM returned an invented `stance` key and omitted seven contract fields. Every omitted field had a default on `CommentAnalysis`, so validation passed and the whole batch silently landed on "无法判断" — the reported 95% manual-review rate. `prompts/comment_analysis_prompt.txt` now enumerates all eight output keys with their allowed values, and `comment_analyzer._check_contract` raises when the model drops them batch-wide, so a broken contract is loud instead of invisible.
- Widened `m=与版本无关` from "anything not mapped to a listed change" to "nothing about the game at all". A comment criticising balance but naming no listed change used to lose its attitude along with its mapping.
- A paraphrased `evidence_quote` no longer costs the whole batch. The longest genuine substring is salvaged; only a fully hallucinated quote is dropped.

### Changed
- **Comments travel as sequence numbers.** Rows go out as `{"n": 7, "t": "..."}` and verdicts come back keyed by `n` instead of echoing a `COM-0042`-shaped id in both directions.
- **The model emits 8 fields instead of 16.** `overall_stance`, `root_issue_status`, `information_quality` and `problem_reason` are derived in Python from direction/intensity/domain (`core.models.apply_derived_fields`), which roughly halves output tokens and makes it impossible for the taxonomy to contradict itself. `reasoning_summary` is no longer requested.
- **The change table is collapsed by target** — 23 rows became 13 on the reference corpus (‑14% payload). The model is only asked for a target, so four Bloodhound rows just forced it to re-decide which ability row a comment meant.
- **Statistics are aggregated per target, not per change row.** A comment naming only a legend belongs to that legend once, not once per ability row.

### Added
- **The human review trail now feeds back into analysis.** `core/review_lessons.py` condenses `review_history` into recurring corrections ("方向态度：人工由「对方向没有明确态度」改为「反对改动方向」（3 例）"), and `services/review_learning.py` optionally has the model generalise them into prose rules, cached on the project and keyed by a fingerprint of the trail. The result is injected into every subsequent analysis batch. The analysis step exposes an "人工复核学习" panel showing the rules and offering 重新归纳 / 清除.
- A "把目标名换成中文" action on the version-import step, for change lists imported before localisation existed.

### Removed
- `PatchChange.change_id` is gone. A change is identified by its target name; `change_key` (target + ability) remains a derived display key. `CommentAnalysis.primary_change_id` / `secondary_change_ids` became `primary_target` / `secondary_targets`. The import step no longer shows or renumber ids.

## [0.7.0] - 2026-09-04

### Changed
- Rebuilt the interface around the main line instead of a menu of workspaces: **提取更新内容 → 评论收集 → 分析评论 → 统计结果**. A single step strip doubles as navigation and as a live progress readout (改动数 / 评论数 / 已分析数 / 待复核数).
- Analysis is now its own step. The review queue moved next to the analysis that produced it, so it is no longer buried behind a separate tab.
- Exports, sampling validation, and direction summaries moved into collapsed panels on the results step.
- Slimmed the sidebar to model configuration and session controls; the prompt editor, alias dictionary, and API console moved into an "高级" expander.
- Deleted `src/ui/overview.py`, the long "识别分类原理 / 实际处理流程" explainer. The step strip replaces it.
- Cleaned up every step page: fewer headings and explanatory captions, more metrics and tables. The change matrix and the cross table now use `ProgressColumn` bars.

### Fixed
- Invalid and duplicate comments no longer enter the human review queue. Analysis never runs on them, so they used to sit there forever with the misleading "尚未完成语义分析" reason — 9 of 200 records on a real corpus.
- The step strip now refreshes project stats before rendering, so it shows live counts instead of whatever the previous session left on disk.

## [0.6.0] - 2026-09-04

### Added
- Analysis progress: a progress bar, an "已分析 N/M 条" counter, the current batch number, and running input/output/reasoning token totals.
- A "停止分析（保留已完成部分）" button. Analysis runs one batch per Streamlit rerun, which keeps the button clickable while a corpus is being processed.
- Resumable analysis: re-running only requests comments that have no analysis yet, so an interrupted run never pays twice for the same comment.

### Changed
- Slimmed the analysis request payload by ~63% on a representative corpus: the confirmed-change table now carries only the seven fields that affect a mapping decision (dropping `source_excerpt`, `design_goal`, `exact_values` and other parser/UI bookkeeping), long prose is clipped, per-comment rows use short keys and omit empty fields, and a source file shared by a batch is hoisted out of the rows.
- Rewrote `prompts/comment_analysis_prompt.txt`: it documents the compact input schema, states the mapping rules explicitly, and caps the free-text output (`reasoning_summary` ≤ 30 字, `evidence_quote` ≤ 20 字, at most 2 short `problem_reason` items).
- `CommentAnalysis` now clamps those free-text fields and splits comma-joined `problem_reason` strings into separate items instead of mangling them into one label.
- Every batch is saved to disk before the next one starts, so stopping, an API error, or closing the tab keeps everything already returned.

## [0.5.0] - 2026-09-02

### Removed
- Deleted the whole screenshot acquisition path: clipboard paste component, file upload, vision/OCR extraction service, image processor, and the demo screenshot generator. Comments now come only from external CSV imports.
- Dropped `image_id`, `ocr_confidence` and `source_image_ids` from the comment contract. All three duplicated `source_file`, and `source_image_ids` was written but never read.
- Removed the "OCR 置信度低于 0.75" review reason, which could no longer fire in a CSV-only pipeline.
- Removed `Pillow` and `streamlit-paste-button` from `requirements.txt`.

### Changed
- Version import and comment analysis now default to `zai-org/GLM-5.3-Flash` with reasoning enabled. GLM-5.x reasoning cannot be turned off, so the client sends `reasoning_effort` instead of `enable_thinking`.
- Added a `reasoning_effort` setting (`low` / `high` / `max`, default `high`). Unknown values are clamped to `high` because the upstream chat template silently resolves them to `max`, the most expensive tier.
- `screenshot_filename` is still accepted when loading older corpora and maps onto `source_file`.
- Replaced the deprecated `use_container_width` argument with `width="stretch"` across the UI (Streamlit 1.60 removed the old name).
- Added `pytest.ini` so collection stays inside `tests/`.

## [0.4.2] - 2026-08-10

- Recovered Windows curl exit 56 only for the exact Schannel missing-close-notify condition after HTTP 2xx, a complete strict JSON document, zero malformed SSE chunks, and full Pydantic validation.
- Forced the curl SSE transport to HTTP/1.1 and tracked DONE, finish reason, malformed chunks, response sizes, and recovery state.
- Disabled every automatic SiliconFlow retry, including empty responses, timeouts, 429, and 5xx, so a second potentially billed request always requires an explicit user action.
- Rejected length, content-filter, and other non-normal finish reasons even when their partial JSON happens to parse.
- Delayed final API success logging until JSON and schema validation complete.
- Added API-console summaries for recovered TLS closure, partial responses, unknown usage, and validation failures.
- Added Fake curl tests proving recovered responses and all failure paths issue exactly one request.
## [0.4.1] - 2026-08-10

- Fixed AI patch summarization when non-hero changes return hero: null.
- Added explicit entity_type, nullable hero, and mandatory normalized target semantics for heroes, weapons, equipment, maps, modes, systems, and bug fixes.
- Recovered valid later aliases such as object when an earlier model alias is null, while keeping genuinely invalid structures strict.
- Normalized explicit null defaults, single exact-value objects, and numeric before/after values without weakening global API response validation.
- Marked truly missing targets or summaries for low-confidence human review instead of discarding the entire generated list.
- Strengthened the patch-structure prompt with a JSON-object contract and hero/non-hero examples.
## [0.4.0] - 2026-08-09

- Added privacy-preserving import for CSV files exported by bilibili-comment-crawler and the author's newer browser extension.
- Added stable anonymous comment fingerprints so incremental exports do not duplicate previously imported comments.
- Preserved reply relationships, likes, publication time, and optional canonical Bilibili source links while discarding usernames, UIDs, avatars, profile details, IP regions, and other account fields.
- Added authorization confirmation, a conservative 200-comment default, a 20 MB file limit, and explicit no-API behavior during import.
- Added Bilibili provenance to review evidence and CSV/JSON exports while anonymizing the original CSV filename.
- Kept screenshot and Ctrl+V vision extraction as a fallback acquisition route.
## [0.3.0] - 2026-08-09

- Corrected the displayed pipeline to the real order: vision extraction, Python cleaning/rules, contextual LLM analysis, then program aggregation and human review.
- Added dynamic stage counts and statuses while moving the full workflow diagram into a compact expander.
- Added per-comment manual keywords and sent platform, likes, reply context, source position, and manual hints to text analysis.
- Prevented repeat OCR calls by default and displayed the expected API call count before execution.
- Connected human review to persistent audit history, expanded editable labels, and retained original/corrected values with changed fields and timestamps.
- Improved sidebar primary-button and dropdown contrast and collapsed the API console unless an error needs attention.
## [0.2.5] - 2026-08-09

- Added a responsive identification-principles and four-stage processing overview to the screenshot workspace.
- Aligned the clipboard paste target with the overview's navy card system and accessible focus state.
- Kept workflow language faithful to the implemented OCR, rule cleaning, alias enrichment, LLM analysis, and human-review pipeline.

## [0.2.4] - 2026-08-02

- Normalized malformed SiliconFlow Base URLs before model-list requests.
- Switched the recommended text model to Qwen/Qwen3-8B for faster structured summaries.
- Increased inference timeout to 180 seconds and disabled automatic retries to prevent duplicate API usage.

## [0.2.3] - 2026-08-02

- Fixed config constant imports during Streamlit hot reload by keeping recommended model display constants local to app.py.

## [0.2.2] - 2026-08-02

- Switched the default SiliconFlow base URL to the official https://api.siliconflow.com/v1 endpoint.
- Added recommended text and vision model defaults and documented that the app uses /chat/completions.
- Disabled thinking for structured text calls and set vision detail to low to reduce token usage.

## [0.2.1] - 2026-08-02

- Fixed Streamlit hot reload compatibility when app.py updates before the cached SiliconFlowClient module.

## [0.2.0] - 2026-08-02

- Changed official patch structuring to an AI-led summary and classification flow with deduplication and hero/ability hierarchy instructions.
- Made screenshot upload state visible and kept the save button stable after file selection.
- Added a visible API console with request status, model, elapsed time, token usage or error details.
- Added a per-session API request limit, 60-second request timeout, and at most one automatic retry to prevent excessive API usage.

## [0.1.1] - 2026-08-02

- Added an in-app close button with confirmation for the local Streamlit service.
- Updated `run_app.bat` so its foreground process owns the app lifecycle.
- Added in-app SiliconFlow API and model selection settings.
- Grouped Passive, Tactical, Ultimate, and New Upgrades under their hero heading.

## [0.1.0] - 2026-08-02

- Initial MVP: EA import, screenshot OCR, comment analysis, transparent metrics, review, validation, and export.
- Added fictional demo data and screenshot evidence.
