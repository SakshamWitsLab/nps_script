# Post-delete verification report

- Generated: 2026-09-17T04:54:36
- Delete mode: `hard`
- Documents affected: **2814** | chunks affected: **36864** | batches: **8** | duration: **4.4s**

## Re-check after delete

  check | count
  ------ | ------
  URL rows still present (any state) | 0
  URL rows still ACTIVE (not deleted / not TRASHED) | 0
  File rows still present (any state) | 0
  File rows still ACTIVE (not deleted / not TRASHED) | 0
  Active chunks still carrying a dropped name | 0

**Result: PASS - nothing of the DROP list is still retrievable.**

## Database snapshot at end

- documents total: **3151** (links 2976, docs 175, soft-deleted 0)
- chunks total: **7262** (active 7262)
