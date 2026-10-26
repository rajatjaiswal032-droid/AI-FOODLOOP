# AI FOODLOOP Development Roadmap

Tracking model: 50 tasks x 2 checkpoints (A = diagnosis/requirements verified, B = implementation + verification completed) = 100 checkpoints.
Score = verified checkpoints / 100 x 100%.

Current verified score: **35%** (historical evidence-based estimate; updated after Task 45 [B] verification).

Legend: [ ] not started, [A] checkpoint A verified, [B] checkpoint B verified.

## Phase 1 - Stability and correctness

1. Quantity calculation consistency - [B] (2026-10-26: `_quantities()` fixed to derive remaining from available/assigned/disposed; regression assertions added)
2. Assignment and delivery accounting - [B] (partial/full/over-allocation covered by tests)
3. Disposal accounting - [B] (double-count prevention tested)
4. Status transitions - [B] (batch/assignment states tested)
5. Database transaction integrity - [A] (transactional writes present; deeper failure tests pending)
6. Quantity precision and units - [A] (numeric validation present; decimal/unit edge cases pending)
7. Concurrent updates - [ ] (not implemented; documented limitation)
8. Database persistence - [B] (isolated temp DBs in tests)
9. Schema migration reliability - [A] (schema init present; migration tests pending)
10. Regression coverage - [B] (redistribution regression assertions present)

## Phase 2 - CSV and data quality

11. Required column validation - [B]
12. File upload safety - [A] (size limits configured; deeper tests pending)
13. Empty file handling - [A]
14. Duplicate record handling - [A]
15. Missing values - [B]
16. Numeric validation - [B]
17. Date validation - [B]
18. Data-quality reporting - [B]
19. Data provenance - [ ] (not implemented)
20. CSV regression suite - [B]

## Phase 3 - Forecasting and production planning

21. Baseline forecast correctness - [B]
22. Insufficient history - [B]
23. Same-weekday forecasting - [B]
24. Safety-buffer configuration - [B]
25. Production quantity calculation - [B]
26. Forecast evaluation - [B]
27. Naive baseline comparison - [A]
28. Forecast uncertainty - [A] (documented as not invented)
29. Forecast explanation - [B]
30. Feedback-data integration - [ ] (design pending)

## Phase 4 - Surplus and redistribution

31. Surplus detection - [B]
32. Batch creation and verification - [B]
33. Safety eligibility rules - [B]
34. Recipient records - [B]
35. Recipient eligibility - [B]
36. Assignment workflow - [B]
37. Delivery lifecycle - [B]
38. Disposal lifecycle - [B]
39. Audit history - [B]
40. End-to-end redistribution test - [A] (service/API tests cover; full automated scenario pending)

## Phase 5 - Reliability, security, and release

41. Authentication review - [B]
42. Authorization review - [B]
43. API security - [B]
44. Dependency review - [A] (warning assessed; no changes)
45. PyArrow workaround validation - [B] (safe HTML table renderer implemented in dashboard/table_utils.py; all st.dataframe calls replaced; 8 regression tests pass; no PyArrow dependency in table rendering)
46. Browser acceptance coverage - [A] (partial manual verification documented)
47. Dashboard usability - [A]
48. Report exports - [B]
49. Documentation and deployment - [B]
50. Final release assessment - [ ] (pending full suite re-run)

## Open blockers

- Git repository reconciled with remote history (commit 23b4be8) and changes pushed.
- Browser acceptance coverage still partial (Task 46).

## Next priority task

Task 46 (browser acceptance coverage) or Task 5/7 (transaction/concurrency hardening); highest-value next code work is expanding authenticated browser acceptance coverage for the full redistribution lifecycle, then re-running the full suite.