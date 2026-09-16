# Gemini teaching review — 2026-09-16

This is an assistant-conducted transcript review, separate from deterministic tests
and structural acceptance. It is not a blind human evaluation or learner study.
Scores follow `evaluation.md`: 0 fails, 1 partial, 2 clear success.

## Failed baseline

Model: `gemini-3.5-flash-lite`. Prompt hash: `93a87461e41c0f80`.
Full synthetic transcript, learning state, event IDs, and trace IDs:
[`gemini-acceptance-failed.json`](gemini-acceptance-failed.json).

| Dimension | Score | Evidence |
| --- | --- | --- |
| Discovery | 1 | T1 asks language/goals; T2 accepts stated needs, but source preference from T3 is not saved. |
| Curriculum | 1 | T2–3 give a brief, provisional outline, but no curriculum record exists. |
| Source honesty | 0 | T3 accurately describes Example Domain, but unrelated original exercises carry its source ID. |
| Language accuracy | 0 | T5 says the past of “go” has three letters; “went” has four. |
| Interaction | 2 | T5 answers the interruption with explanation and a hint, without requiring a rigid lesson phase. |
| Feedback | 2 | T4 identifies regular-past overgeneralization respectfully; the hint request is not assessed as failure. |
| Assistance | 1 | T6 verbally recognizes help, but does not persist the successful retry. |
| Adaptation | 1 | T7 references prior error evidence but nearly repeats the previous follow-up task. |
| Memory | 1 | T7 uses stored evidence after restart; omitted curriculum and retry limit its accuracy. |

Result: **not a quality pass**. Structural acceptance independently failed three
checks. This baseline motivated prompt-level persistence, provenance, and hint
accuracy changes; the acceptance messages were not changed to make the test easier.

## Revised live run

Model: `gemini-3.5-flash-lite`. Prompt hash: `22ec25eec58b18c1`.
[`gemini-acceptance.json`](gemini-acceptance.json) preserves the transcript and state.
All seven structural checks passed; this does not imply all quality dimensions pass.

| Dimension | Score | Evidence |
| --- | --- | --- |
| Discovery | 2 | T1 asks language/goals; T2 offers relevant choices; all six stated profile fields are saved by T3. |
| Curriculum | 2 | T3 presents and saves a brief provisional outline tied to goals. |
| Source honesty | 2 | T3 accurately quotes and attributes the retrieved page; original exercises now have empty source IDs. |
| Language accuracy | 1 | The four-letter hint is correct, but “irregular” does not always mean changing completely; “walking store” is unnatural. |
| Interaction | 2 | T5 answers the learner's question during practice, without enforcing stages. |
| Feedback | 2 | T4 identifies the specific error and invites a retry; no evidence is recorded for the hint request. |
| Assistance | 1 | T6 success is persisted as assisted, never independent, but the label is “hint” although T4 already showed the answer. |
| Adaptation | 1 | T7 action cites assisted-success evidence but resumes the unanswered T6 exercise instead of generating a different one. |
| Memory | 2 | Restart retains all stated profile fields, curriculum, error and assisted success; no repeated onboarding. |

Result: **structural demonstration passed; teaching quality partial**. The core
independent-versus-assisted distinction works in this run, but assistance severity
is under-recorded because the T4 answer reveal was not separately logged. Code can
conservatively aggregate recorded help; it cannot infer all omitted pedagogical
events from free-form prose. This remains an explicit next evaluation target.

No learner study or general multilingual quality claim follows from this result.

## Evaluation limits

The scenario tests one synthetic A2 English learner, one irregular verb, and a tiny
public web page. It does not establish multilingual reliability, retention gains,
age suitability, or resistance to all source prompt injections. Immediate practice,
unavailable retrieval, independent success, and ownership boundaries have mocked
contract coverage; they still need broader live teaching review.
