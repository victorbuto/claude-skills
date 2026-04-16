---
name: Deep-web-search
description: Advanced keyword generation and web search using the Slice Method. Use when the user needs to generate effective search queries, find information beyond surface-level results, or bypass commercial noise in search engines. Triggers on requests for "search keywords", "find information", "research", "search strategy", or when the user struggles to find relevant results with basic searches. This skill focuses on search execution without fact-checking — pair with a fact-checking skill for verification.
---

# Slice Search Skill

5 steps: receive question → clarify → plan queries → approve → 3 parallel subagents search & analyze → merge.

## Phase 0: Receive the Research Question

**IMPORTANT: Do NOT ask any questions until the user has provided their research topic/question.** If the user's message already contains a clear research question — proceed to Phase 1 (SPICE). If the message is vague or just triggers the skill without a specific question, respond with:

```
Какой вопрос будем исследовать?
```

**STOP here and wait for the user's research question before proceeding.**

---

## Phase 1: Clarify the Research Question (SPICE)

Once you have the user's research question, ask **5 clarifying questions** using the **SPICE framework** (adapted from academic research methodology: Setting, Perspective, Interest, Comparison, Evaluation).

The goal: expose blind spots and hidden assumptions in the user's request.

**Ask these 5 questions and wait for answers before proceeding to Phase 2:**

| # | SPICE element | Question to ask | What it reveals |
|---|---------------|-----------------|-----------------|
| 1 | **Setting** | Какая география, отрасль, сегмент рынка? Есть ли временные рамки (последний год, 5 лет, всё время)? | Boundaries — сужает область поиска |
| 2 | **Perspective** | Чей взгляд важен — бизнес, академия, потребители, инвесторы? Для какой аудитории результат? | Angle — определяет тип источников и язык |
| 3 | **Interest** | Что конкретно нужно найти — обзор темы, конкретные цифры/данные, кейсы, список игроков, тренды? | Depth — задаёт глубину и формат поиска |
| 4 | **Comparison** | Есть ли с чем сравнивать? Нужен бенчмарк (другая страна, период, конкурент)? | Contrast — добавляет сравнительное измерение |
| 5 | **Existing knowledge** | Что уже знаете по теме? Какие источники/статьи уже видели? Что НЕ нужно искать? | Gaps — исключает дубли, фокусирует на белых пятнах |

**Format for asking:**
```
Перед поиском уточню 5 вопросов по фреймворку SPICE:

1. **Рамки:** [вопрос адаптированный к теме]
2. **Перспектива:** [вопрос]
3. **Что ищем:** [вопрос]
4. **Сравнение:** [вопрос]
5. **Уже знаете:** [вопрос]
```

After user answers, incorporate their responses into Phase 2 analysis as constraints.

---

## Phase 2: Plan Search Queries

Use SPICE answers to inform query generation.

### 2.1 Analyze the Query

- **Core topic** — main subject (from user request + SPICE answers)
- **Goal** — facts, sources, opinions, data, comparison (from SPICE #3 Interest)
- **Query type** — classify for slice distribution
- **Constraints** — from SPICE #1 Setting + #2 Perspective + #5 Existing knowledge

| Query Type | Primary Slices | Secondary Slices |
|------------|----------------|------------------|
| **Factual/Statistical** | Source, Authority, Peristatic | Regional, Syntactic |
| **Technical/Expert** | Specific Term, Metonymical, Source | Syntactic, Authority |
| **Current Events** | Source, Regional, Authority | Peristatic |
| **Historical/Academic** | Syntactic (filetype), Authority, Source | Regional, Metonymical |
| **Comparative** | Regional, Source, Authority | Metonymical |
| **Niche/Obscure** | Specific Term, Syntactic, Peristatic | Regional, Source |

### 2.2 Generate 20+ Search Queries

Use **7 slice types** (see [references/slice-method.md](references/slice-method.md)):

| Slice | What It Does |
|-------|--------------|
| **Regional** | Other languages/markets |
| **Authority** | Known institutions/experts |
| **Source** | Specific platforms/databases |
| **Specific Term** | Niche expert terminology |
| **Syntactic** | Alt spellings, scripts, filetypes |
| **Metonymical** | Adjacent/related concepts |
| **Peristatic** | Quotes, contextual fragments |

**Key:** Rare terms > generic terms.

Distribution by type:

| Query Type | Reg | Auth | Source | Spec | Synt | Meton | Perist |
|------------|-----|------|--------|------|------|-------|--------|
| Factual | 2 | 3 | 8 | 2 | 1 | 1 | 3 |
| Technical | 1 | 2 | 4 | 5 | 3 | 4 | 1 |
| News | 3 | 3 | 9 | 1 | 1 | 1 | 2 |
| Academic | 2 | 4 | 4 | 2 | 4 | 2 | 2 |
| Comparative | 5 | 3 | 6 | 2 | 1 | 2 | 1 |
| Niche | 3 | 1 | 1 | 5 | 4 | 3 | 3 |

### 2.3 Present to User

**STOP. Show the query list and wait for approval:**

```
## Search Plan: [Topic]
**Type:** [Classification] | **Queries:** [N]

| # | Slice | Query | Why |
|---|-------|-------|-----|
| 1 | Source | `site:statista.com ...` | Stats |
| ... | ... | ... | ... |

Approve, edit, or add?
```

---

## Phase 3: Search & Analyze (3 parallel subagents)

After user approves, split queries into 3 groups and launch **3 subagents in parallel**. Each subagent searches AND analyzes within its own context window.

### Subagent prompt template

```
Task(subagent_type="general-purpose", prompt="
  You are a research agent. Your task:

  1. SEARCH: Execute these queries using tavily_search.
     For each query: search_depth='advanced', include_raw_content=true, max_results=5

     Queries:
     1. [query]
     2. [query]
     ...

  2. ANALYZE: Read through all results (snippets + raw_content).
     Extract: facts, statistics, expert quotes, case studies, contradictions.
     Drop results with score < 0.3. Deduplicate by URL.

  3. RETURN exactly this format:

     ## Round [N] Results

     **Queries executed:** [N]
     **Results found:** [N] unique after dedup

     ### Key Findings
     [Every fact, statistic, or claim with inline source link:
     'fact or data — [Source Name](URL)']

     ### Source List
     | # | Title | URL | Score | What it contributed |
     |---|-------|-----|-------|---------------------|

     ### Gaps
     [What queries returned nothing useful, what's missing]
")
```

**Launch all 3 in parallel in a single message:**
- Subagent 1: queries 1-8 (priority slices)
- Subagent 2: queries 9-15 (secondary slices)
- Subagent 3: queries 16-22+ (adaptive, gap-filling)

### What main context receives

3 structured summaries (~3-5KB each) with pre-analyzed findings and inline sources. NO raw page content in main context.

---

## Phase 4: Merge & Synthesize

Combine findings from all 3 subagents into final output.

### 4.1 Merge

- Combine Key Findings from all rounds
- Deduplicate facts (same stat from different sources → keep best source)
- Note contradictions between rounds

### 4.2 Output

**Source attribution rule:** Inline hyperlink right after the fact it supports: `fact — [Source Name](URL)`. Do NOT collect sources into a separate table at the bottom.

```markdown
## Research: [Topic]

**Queries:** [N] | **Sources found:** [N] | **Rounds:** 3

### Key Findings
[Synthesized answer organized by themes/subtopics.
Each fact, statistic, or claim has an inline source link:
"fact or data — [Source Name](URL)"]

### Search Effectiveness

| Metric | Details |
|--------|---------|
| **Best slices** | [slice type] — [why it worked, example result] |
| **Failed slices** | [slice type] — [why it failed or returned noise] |
| **Gaps** | [what's missing] |
| **Follow-up queries** | `query 1`, `query 2` |
```

## Quick Reference

| Slice | Example |
|-------|---------|
| Regional | `AI news` → `actualités IA France` |
| Authority | `climate` → `IPCC report findings` |
| Source | `AI` → `site:arxiv.org transformer` |
| Specific Term | `coffee` → `anaerobic fermentation` |
| Syntactic | `report` → `filetype:pdf quarterly` |
| Metonymical | `blockchain` → `Byzantine fault tolerance` |
| Peristatic | `article` → `"absorbs 30 percent"` |
