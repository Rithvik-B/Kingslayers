# Ideas

One file per idea: `docs/ideas/<short-slug>.md`. Anyone can add one. Add a comment or a score to a
teammate's idea under "Team notes" instead of rewriting their pitch.

When the team picks an idea, record it with `/decide`. Then set the chosen idea's status to `chosen` and the
others to `parked`.

## How to score (1-5 each)

These come from the themes deck (`competition-info/themes.md`) and what earlier winners had in common
(`competition-info/contextcon-winning-submissions.md`).

| Criterion | What a 5 looks like |
|---|---|
| **Replaces a paid service** | The agent does the whole job a person is paid for, end to end, without a human approving each step. |
| **Can be proven on past data** | There is a clear "We're looking for" style test: run it on past data, using only what was known at each date, and show a score. |
| **Crustdata is central** | People and company data does the main work. It isn't decoration. |
| **Demo moment** | A non-technical user, at the moment of a real decision, can see the value within 3 minutes. |
| **Not crowded** | Not another generic recruiting, sales-outreach or VC-scouting tool. Past editions had many of those, and most didn't place. |
| **Buildable in time** | A working demo fits in the build window with our team's skills. Fake nothing that is on the critical path. |
| **We have insight** | Someone on the team knows this problem from the inside. Edition 1's winner was a team of domain experts. |

## Template

```markdown
---
title: <name>
author: <name>
theme: <one of the 10 themes, or "own idea">
status: draft | shortlisted | chosen | parked
---

## One-liner
<Who> pays <whom> to do <what> today. Our agent does it by <how>.

## The service it replaces
Who does this job today, what they are paid, and why it is hard.

## How it works
Inputs, then agent steps, then output. Which Crustdata APIs it uses and what data it needs from them.

## How we prove it works
The past-data test or evaluation, and which metric we show the judges.

## Demo (3 min)
What the judges see, step by step. What is the "wow" moment?

## Risks / unknowns
Data gaps, API limits, things we haven't verified yet.

## Scores
| Paid service | Past data | Crustdata | Demo | Not crowded | Buildable | Insight | Total |
|---|---|---|---|---|---|---|---|
| | | | | | | | /35 |

## Team notes
- <name>: <comment>
```
