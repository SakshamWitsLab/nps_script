# KEEP verification report (check-report)

- Generated: 2026-09-17T05:16:29
- Database: `nps_chatbot_hard`
- Workbook: `/home/saksham/Downloads/nps_script/NPS_RAG_Ingestion_Review_TRIAGED.xlsx`
- KEEP sheets: `KEEP - URLs` / `KEEP - Documents`
- Pass criteria: every KEEP target must have an active/retrievable document AND must not have lost chunks it had in the baseline. The KEEP sheets must not overlap the DROP sheets.
- Chunk matching is by identity (`document_chunks.doc_name`), not by the container `document_id`.
- Baseline database: `nps_chatbot` (chunk regression comparison enabled)

## Summary

  KEEP target state | URLs | files | total
  ----------------- | ------ | ------ | ------
  PRESENT_ACTIVE (retrievable) | 70 | 38 | 108
  CHUNKS_LOST (doc live, chunks gone) | 0 | 0 | 0
  PRESENT_INACTIVE (soft-deleted/TRASHED) | 0 | 0 | 0
  MISSING (no DB row) | 0 | 0 | 0
  TOTAL targets | 70 | 38 | 108

- KEEP URL targets: `70` | KEEP file targets: `38` | total `108`
- Present & retrievable: **108** / 108
- Matched DB documents (all states): **360**
- KEEP chunks by doc_name: total **2241**, active **2241** (baseline **2241**)
- Chunk regressions (chunks lost vs baseline): **0**

**Result: PASS - every KEEP target is present and retrievable.**

## KEEP vs DROP disjointness

- URL targets present in both KEEP and DROP: **0**
- File targets present in both KEEP and DROP: **0**

## URL targets needing attention (0)

All URL targets are present and retrievable.

## file targets needing attention (0)

All file targets are present and retrievable.
