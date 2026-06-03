---
name: thai-token-economy
description: Token-efficient discipline for a Thai-speaking session — keep the Thai UX, cut the token cost, with NO loss of capability. The lever is LAYER SEPARATION — human I/O in Thai (the user's prompts + your final reply), but every machine-facing artifact AND your internal reasoning in English (code, comments, identifiers, commit messages, PR titles/bodies, log lines, test names, sub-agent prompts, scratch reasoning), and Thai replies kept concise (tables + English identifiers over long Thai connective prose). Honest about the tokenizer — Thai costs ~2-4x tokens per character vs English, so "Thai == English cost" is impossible; this discipline closes most of the gap instead. TRIGGER at the start of any non-trivial multi-step task in a Thai-language session, when the user says "ประหยัด token" / "ตอบสั้นๆ" / "คุยไทยแต่ให้ประหยัด" / "ใช้ token เยอะ" / "ทำไม token เยอะ" / "why so many tokens", or as the standing style whenever a session is conducted in Thai. SKIP for English-only sessions (nothing to optimize), and never let concision suppress a real finding / warning / caveat — concision drops redundant glue, not substance.
---

# Thai Token Economy

How to run a Thai-language session at near-English token cost **without
dropping any capability**. This skill's body is written in English on
purpose — that IS the discipline (machine-facing artifacts stay English;
only the human-facing reply is Thai).

## The honest premise (don't sell a false promise)

Claude's tokenizer encodes Thai far less efficiently than English:

- Thai script is multi-byte UTF-8 and has **no spaces between words**, so
  the BPE tokenizer falls back to tiny sub-word / byte-level units.
- Empirically Thai runs **~2-4x tokens per character** vs the same meaning
  in English.

So **"reply in Thai as cheaply as English" is impossible at the token
level.** Anyone who claims otherwise is wrong. The achievable win is
different and large: **most tokens in a coding session are NOT the chat** —
they are tool calls, code, file content, logs, diffs, reasoning, and
sub-agent prompts. Keep all of THAT in English (where it belongs anyway)
and make only the small human-facing reply Thai-and-concise. That closes
most of the gap.

## The lever: layer separation

| Layer | Language | Why |
|---|---|---|
| User's prompt | Thai (as they write) | their choice — untouched |
| **Your final reply to the user** | **Thai, concise** | the only part that must be Thai |
| Internal reasoning / scratch / planning | **English** | model reasons equally well; far cheaper |
| Code, identifiers, comments | **English** | project convention + cheaper |
| Commit messages, PR title/body | **English** | project convention + cheaper |
| Log lines, test names, error strings | **English** | cheaper; also grep-friendly |
| Sub-agent prompts you author | **English** | cheaper; agents are English-native |
| Tables / numbers / file paths in a Thai reply | **stay English/ASCII** | a path or `ScoreGauge.tsx` is the same tokens in any reply language |

The rule of thumb: **Thai is for the human; English is for the machine and
for your own thinking.**

## Rules

1. **Think in English, answer in Thai.** Your chain-of-thought, your
   plans, your intermediate notes — English. Translate to Thai only at the
   final user-facing sentence(s).
2. **Never write Thai into the repo.** Code, comments, docstrings, commit
   messages, PR bodies, doc files = English (already the project standard —
   see AGENTS.md §Code style). A Thai code comment is both off-convention
   and ~3x the tokens.
3. **Concise Thai, not terse Thai.** Drop connective glue
   ("จากการที่ผมได้ทำการตรวจสอบแล้วพบว่า…" → "ตรวจแล้ว:"), not findings.
   Prefer **tables, bullet lists, and English identifiers** over long Thai
   sentences — Thai prose glue is the expensive part; a table of numbers is
   nearly language-neutral.
4. **Say it once.** Don't state a term in English then re-explain the same
   thing in Thai, or repeat the conclusion in both languages. One channel.
5. **Lead with the answer.** Put the result/number/decision first; add
   rationale only if it changes what the user does. Skip the "ผมจะ…"
   preamble and the "หวังว่าจะช่วยได้" outro.
6. **Delegate the bulk.** Sub-agents do their long reading/auditing in
   their own (English) context; you receive their report and emit a short
   Thai synthesis. This keeps the token-heavy work off the main reply
   entirely (and drains the paid Sonnet pool — see CLAUDE.md §Auto-routing).

## Do / Don't (Thai reply examples)

**Don't** (verbose Thai glue, restated, padded):
> จากการที่ผมได้ทำการตรวจสอบไฟล์ `RankingTable.tsx` อย่างละเอียดแล้ว ผมพบว่า
> มีปัญหาเกี่ยวกับการใช้งาน loose null check อยู่ทั้งหมดสองจุดด้วยกัน ซึ่งจุดแรกนั้น
> อยู่ที่บรรทัดที่ 268 และอีกจุดหนึ่งอยู่ที่บรรทัดที่ 312 … (ต่ออีกยาว)

**Do** (lead with answer, table, English identifiers, no glue):
> เจอ loose-null 2 จุดใน `RankingTable.tsx`:
> | บรรทัด | ปัญหา | แก้เป็น |
> |---|---|---|
> | 268 | `=== null` | `== null` |
> | 312 | `=== undefined` | `== null` |

Same information, a fraction of the tokens — and the table cells that carry
the actual signal are mostly ASCII.

## Where the tokens actually go (optimize the right thing)

In a typical QuantRank coding turn, the Thai chat reply is a **small**
share of total tokens. The big consumers are: the always-loaded CLAUDE.md
(kept lean — §Conventions "CLAUDE.md is an INDEX"), tool outputs (read
only the lines you need — use `offset`/`limit`, `sed -n`, `grep -n`),
sub-agent context windows, and your own reasoning. **Optimizing those
beats agonizing over the Thai reply.** So: this skill's Thai-reply rules
are the *finishing* move; the *structural* wins are lean context + targeted
reads + delegation.

## What concision must NOT do

- Do **not** drop a real finding, warning, caveat, risk, or a "this failed"
  result to be shorter. Report outcomes faithfully (a failed test is stated
  with its output, in Thai if that's the reply channel).
- Do **not** skip the destructive-action confirmation, the schema/lockstep
  reminder, or any safety gate to save tokens.
- Do **not** compress to the point of ambiguity. If the user must re-ask,
  the "saving" cost more than it saved.

Concision is about **glue and repetition**, never about substance.

## Quick self-check before sending a Thai reply

- Answer/number first? · Any English-then-Thai duplication to cut? · Could
  a 3-line table replace a paragraph? · Any Thai that's actually a code
  identifier / path (leave it ASCII)? · Did I keep every real finding?
