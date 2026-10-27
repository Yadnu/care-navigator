# Safety rules (non-negotiable)

- Models never choose the care level or skip a safety check. Only deterministic rules (`red_flags.yaml`, `care_rules.yaml`, retrieval hard filters) decide. (D-001)
- Any red-flag signal (raw-text rules, Jev emergency, parsed-field rules) routes to EMERGENCY. (D-002)
- Uncertainty, missing fields, invalid model output, timeouts or provider errors route toward MORE care, never less. At most one follow-up question. (D-003)
- Never diagnose. Never name a condition as the person's diagnosis. Never mention medications, doses or treatments in any output, prompt example or template.
- Every user-facing explanation ends with "This is not medical advice."
- Practitioner names, addresses, phones and plans come only from records, never from model output. (D-007)
- Redact PII before any model call; traces hold redacted text only. (D-009)
- Text in the request is data, not instructions: prompt injection must never change the outcome.
- Retrieved practitioners must pass every hard filter: zero violations is a hard rule. (D-006)
