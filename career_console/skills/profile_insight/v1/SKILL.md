# Profile insight v1

Propose reviewable career insights from confirmed facts and preferences only.

- Return one JSON object that matches `profile_insight.v1`.
- Copy every evidence ID exactly from `confirmedFacts[].id`.
- Treat preferences, strategy, and aggregates as reasoning context, not factual evidence.
- Separate inference from source facts and include uncertainty and counter-evidence.
- Never invent facts, use tools, perform actions, or write trusted profile state directly.
