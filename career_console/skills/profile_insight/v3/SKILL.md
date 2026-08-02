# Profile insight v3

Generate the user's current categorized career guidance from trusted CareerConsole state.

- Return one JSON object matching `profile_insight.v3`.
- The only categories are `interview`, `application`, `resume`, `learning`, and
  `career_direction`.
- Each item contains an `analysis` and a concrete `recommendation`.
- Write every `analysis` and `recommendation` in concise Simplified Chinese. Technical names may
  remain in English where appropriate, but the prose must remain Chinese-dominant.
- Do not create a strengths section, priority ranking, weekly plan, or generic next-step section.
- `interview` emphasizes confirmed interview improvement items and repeated interview issues.
- `application` emphasizes confirmed preferences, application status aggregates, and recent
  application behavior.
- `resume` emphasizes confirmed facts, evidence completeness, and target-role alignment.
- `learning` emphasizes repeated skill gaps and questions the user could not answer well.
- `career_direction` emphasizes stable preferences, constraints, and outcome patterns.
- Omit a category when trusted input cannot support useful guidance for it.
- Copy fact IDs exactly from `confirmedFacts[].id`.
- Copy interview improvement IDs exactly from `confirmedInterviewImprovements[].id`.
- Every item must cite at least one trusted fact or improvement ID.
- Preferences and aggregates are reasoning context, not evidence IDs.
- Results are automatically published advisory guidance. Never ask for confirmation or mutate
  formal business state.
- Do not invent facts, use tools, or include fields outside the contract.
