# Sensor-loss policy: offline first stage of #204

`HHM3SensorLossPolicy.js` is a pure ECMAScript 5 decision helper,
**not yet connected to the circuit controller**. It reads no physical
channels and cannot command a relay, mixer, boiler or pump.

Intended sequence:

1. Brief supply-sensor invalidity: `HOLD_LAST_ACCEPTED`, preserve
   the previously accepted valve position and demand without new writes.
   A fallback command must not be treated as accepted until the upstream
   writer explicitly reports acceptance; neither implies valve travel.
2. Prolonged invalidity: `LIMITED_HEAT` with a **nonzero,
   explicitly object-approved position**, only after independent
   temperature/safety evidence and hydraulic path are confirmed.
3. Unapproved fallback or unsafe/unknown path: return a distinct
   diagnostic state; do not silently choose `valve=0`, `pump=OFF`,
   or an unbounded heat request. Higher-level engineering policy needed.
4. Stable sensor recovery: resume ordinary mixer ownership.
   Brief sensor flapping must not restart the full HOLD grace.

**Test fixture values (15 s, 18%, 10 s) are not commissioned
limits for any object.** No fallback numbers may be copied to Iset or
Ivolga without independent approval and physical verification.

This module is preparatory work. Integration remains to be designed
with `HHM3Circuit` / `HHM3Mixing`, health semantics, single output
writer, thermal protections, startup/postrun and independent fallback
authorizations. No unverified physical flow claims.

Run: `node Systems/HHM/tests/sensor-loss-policy.js`

No live changes, merge, deployment or release approval.
