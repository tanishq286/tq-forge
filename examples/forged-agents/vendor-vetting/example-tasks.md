## Task 1 — name only
Input: "Vet Acme Components Pvt Ltd before we sign a supply contract."
Expected: a VENDOR RISK BRIEF with legal-entity status, operating history,
independent evidence, any red flags, and a GO/CAUTION/NO-GO call with a flip
condition.

## Task 2 — name + site, marketing claims present
Input: "Check northstar-logistics.example — their site says 'ISO 9001 certified,
500+ clients'."
Expected: the ISO and client-count claims listed under CLAIMS (unverified), an
attempt to corroborate the ISO cert against the issuing registry, and the
recommendation gated on whether corroboration succeeds.

## Task 3 — red flag surfaced
Input: "Due diligence on Meridian Trade FZE."
Expected: if research surfaces a dissolved entity or active litigation, a NO-GO
(or CAUTION) with the red flag ranked by severity and cited, and the flip
condition naming what evidence would clear it.
