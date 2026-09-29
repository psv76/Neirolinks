# pressure_makeup 1.0

Baseline for `05_31_Ivolga_13`, boiler `wirenboard-ABF62SL`.
The author reviewed exported live bytes in
https://github.com/psv76/Neirolinks/pull/71#issuecomment-5809077082:
the live 507 equals the repository copy except for its missing final LF.
The component decision is recorded in
https://github.com/psv76/Neirolinks/pull/71#issuecomment-5809381674.

This artifact is reconstructed from the exact Git blob
`d75710dad93906af8869dcce48d26e14673b63fb:objects/05_31_Ivolga_13/Wirenboard/wb-rules/507_Pressure_makeup.js`
by removing exactly one terminal LF. No other bytes, logic, thresholds or
runtime behavior are changed. No live controller was accessed to create it.
Tests assert the exact relationship; runtime never normalizes payload bytes.
Field check must still compare the actual live SHA256 against this baseline.

Version `1.0` is external release metadata in the NLI manifest; the legacy JS
has no runtime version control. No version comment is injected into baseline.
The standalone owner of A04/K1 remains this rule. A wb-rules restart resets
pulseCount/alarm flags and runs normal init/evaluate, as explicitly accepted.
