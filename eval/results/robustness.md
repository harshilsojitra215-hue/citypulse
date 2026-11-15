# Edited-post test (answers fixed by the edit)

179 items: edits of real pilot posts where all 3 AI labellers agreed, plus written templates. For real-post edits the expected label comes from the same labeller's own label on the original post plus one codebook rule. Blind labelling runs: haiku (179 labels), sonnet_a (179 labels), sonnet_b (179 labels). Intervals: Wilson 95%.

| Test | What it checks | haiku | sonnet_a | sonnet_b | majority_3 |
|---|---|---|---|---|---|
| E1_project_swap | Heilbronn and Bonn swapped in the text: project must swap, stance must stay | 13/19 (68%, 46% to 85%) | 19/19 (100%, 83% to 100%) | 19/19 (100%, 83% to 100%) | 19/19 (100%, 83% to 100%) |
| E2_quoted_in_report | opinion post quoted inside a neutral news report: must become neutral | 29/29 (100%, 88% to 100%) | 5/29 (17%, 8% to 35%) | 5/29 (17%, 8% to 35%) | 6/29 (21%, 10% to 38%) |
| E3_cost_but | support post + "good idea, but far too expensive": must become mixed | 16/17 (94%, 73% to 99%) | 5/17 (29%, 13% to 53%) | 17/17 (100%, 82% to 100%) | 16/17 (94%, 73% to 99%) |
| E4_tone_caps | "WICHTIG!!!" added: nothing may change | 26/29 (90%, 74% to 96%) | 28/29 (97%, 83% to 99%) | 28/29 (97%, 83% to 99%) | 28/29 (97%, 83% to 99%) |
| E5_sidebar | link list naming Heilbronn appended: nothing may change | 30/30 (100%, 89% to 100%) | 30/30 (100%, 89% to 100%) | 30/30 (100%, 89% to 100%) | 30/30 (100%, 89% to 100%) |
| E6_numbers | amounts changed (157 -> 164 Millionen): nothing may change | 18/20 (90%, 70% to 97%) | 20/20 (100%, 84% to 100%) | 20/20 (100%, 84% to 100%) | 20/20 (100%, 84% to 100%) |
| T1_flip_pair | written pairs, one phrase flips for/against | 14/14 (100%, 78% to 100%) | 14/14 (100%, 78% to 100%) | 14/14 (100%, 78% to 100%) | 14/14 (100%, 78% to 100%) |
| T2_angry_support | angry words but wants it built: support | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T3_calm_oppose | calm, friendly words but wants it stopped: oppose | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T4_council_report | report of a council decision: neutral | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T5_reported_opposition | news reports a group demanding a stop: neutral | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T6_neutral_question | neutral question ("where will cars park?"): neutral | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T7_mixed | idea good, cost too high: mixed | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| T8_irrelevant_lift | ski or playground lift: irrelevant | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) | 3/3 (100%, 44% to 100%) |
| directional (must change) |  | 80/81 (99%, 93% to 100%) | 45/81 (56%, 45% to 66%) | 57/81 (70%, 60% to 79%) | 57/81 (70%, 60% to 79%) |
| invariance (must not change) |  | 87/98 (89%, 81% to 94%) | 97/98 (99%, 94% to 100%) | 97/98 (99%, 94% to 100%) | 97/98 (99%, 94% to 100%) |
| all |  | 167/179 (93%, 89% to 96%) | 142/179 (79%, 73% to 85%) | 154/179 (86%, 80% to 90%) | 154/179 (86%, 80% to 90%) |

## Failures of the 3-run majority (what the system would publish)

- E2_quoted_in_report E001 (seed P229): stance: got support, expected neutral_informative
- E2_quoted_in_report E008 (seed P155): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E014 (seed P207): stance: got support, expected neutral_informative
- E2_quoted_in_report E016 (seed P078): stance: got support, expected neutral_informative
- E2_quoted_in_report E017 (seed P112): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E048 (seed P012): stance: got support, expected neutral_informative
- E2_quoted_in_report E055 (seed P081): stance: got support, expected neutral_informative
- E2_quoted_in_report E057 (seed P086): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E068 (seed P109): stance: got support, expected neutral_informative
- E2_quoted_in_report E071 (seed P234): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E079 (seed P138): stance: got support, expected neutral_informative
- E2_quoted_in_report E083 (seed P227): stance: got support, expected neutral_informative
- E2_quoted_in_report E085 (seed P170): stance: got None, expected neutral_informative
- E2_quoted_in_report E095 (seed P151): stance: got support, expected neutral_informative
- E2_quoted_in_report E097 (seed P038): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E109 (seed P199): stance: got support, expected neutral_informative
- E2_quoted_in_report E133 (seed P148): stance: got support, expected neutral_informative
- E2_quoted_in_report E136 (seed P066): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E153 (seed P126): stance: got support, expected neutral_informative
- E2_quoted_in_report E159 (seed P185): stance: got support, expected neutral_informative
- E2_quoted_in_report E161 (seed P006): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E168 (seed P099): stance: got oppose, expected neutral_informative
- E2_quoted_in_report E170 (seed P107): stance: got oppose, expected neutral_informative
- E3_cost_but E164 (seed P170): stance: got support, expected mixed
- E4_tone_caps E041 (seed P099): project: got None, expected heilbronn_cablecar

Known test-design issues (found after scoring, kept visible): (1) E2 extends codebook stance rule 1, which names "a quote of a politician", to a long citizen opinion quoted inside a news item. The codebook does not say this case explicitly, so E2 failures show a codebook gap, not only model errors. (2) Some E1 swaps create impossible text (Bonn inside "Baden-Württembergs erste Nahverkehrs-Seilbahn", seeds P096, P116, P150), so a few haiku E1 misses are partly the edit's fault.

Limits: the edits and templates were written by Claude with the codebook open, so they test whether the labeller follows the codebook rules, not whether the rules match how people read real posts. Edited text is cleaner than real language. Seeds are posts all 3 AI runs agreed on (easier posts).

