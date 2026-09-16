# Pre-delete report

- Generated: 2026-09-17T05:17:10
- Workbook: `/home/saksham/Downloads/nps_script/NPS_RAG_Ingestion_Review_TRIAGED.xlsx`
- URL sheet: `DROP - URLs` | file sheet: `DROP - Documents`
- Delete mode: `hard` | DRY_RUN: `True`

## Workbook targets

- URL rows in sheet: `822` (skipped empty: `0`, header-artifact rows ignored: `1`)
- URL target values: `1643` (distinct normalized: `894`) [example_url=822, canonical=821]
- File rows in sheet: `189` (skipped empty: `0`)
- File target values: `189`

## Detected in database

- URL documents matched: **0**
- DOCUMENT rows matched: **0**
- Total documents to remove (after expansion): **0** (expanded via supersedes/children: **0**)
- Chunks attached (by container document_id): total **0**, active **0**

### Chunk plan (identity = `document_chunks.doc_name`)

- Chunks to delete by identity: **0** (URL **0** / file **0**)
- KEEP chunks preserved: **2241**
- Other (untouched) chunks preserved: **5021**
- Surviving chunks reparented off DROP containers: **0**
- Reparent anomalies (no surviving owner): **0**

### Breakdown by status / source type (matched rows)

  status | count
  ------ | ------

Matched rows by source type: 

Rows that are parent docs: `0` | rows superseded at match time: `0`

## Targets with no database match (informational)

- URL targets with no match: **894**

  # | normalized target | source values
  ------ | ----------------- | -------------
  1 | 56677 | 56677
  2 | npstrust.org.in | https://npstrust.org.in/, npstrust.org.in/
  3 | npstrust.org.in/5-reasons-why-you-should-start-investing-national-pension-system-nps-first-week-april-2025 | https://npstrust.org.in/5-reasons-why-you-should-start-investing-national-pension-system-nps-first-week-april-2025, npstrust.org.in/5-reasons-why-you-should-start-investing-national-pension-system-nps-first-week-april-2025
  4 | npstrust.org.in/5-reasons-why-you-should-start-investing-nps-first-week-april-2025 | https://npstrust.org.in/5-reasons-why-you-should-start-investing-nps-first-week-april-2025, npstrust.org.in/5-reasons-why-you-should-start-investing-nps-first-week-april-2025
  5 | npstrust.org.in/6-income-tax-saving-ways-investors-optimise-returns-nps-scheme | https://npstrust.org.in/6-income-tax-saving-ways-investors-optimise-returns-nps-scheme, npstrust.org.in/6-income-tax-saving-ways-investors-optimise-returns-nps-scheme
  6 | npstrust.org.in/about | https://npstrust.org.in/about, npstrust.org.in/about
  7 | npstrust.org.in/about-apy | https://npstrust.org.in/about-apy, npstrust.org.in/about-apy
  8 | npstrust.org.in/about-msf | https://npstrust.org.in/about-msf, npstrust.org.in/about-msf
  9 | npstrust.org.in/about-nps | https://npstrust.org.in/about-nps, npstrust.org.in/about-nps
  10 | npstrust.org.in/about-nps-trust | https://npstrust.org.in/about-nps-trust, npstrust.org.in/about-nps-trust
  11 | npstrust.org.in/about-nps-vatsalya | https://npstrust.org.in/about-nps-vatsalya, npstrust.org.in/about-nps-vatsalya
  12 | npstrust.org.in/accessibility | https://npstrust.org.in/accessibility, npstrust.org.in/accessibility
  13 | npstrust.org.in/act-and-regulations | https://npstrust.org.in/act-and-regulations, npstrust.org.in/act-and-regulations, https://npstrust.org.in/act-and-regulations?page=0
  14 | npstrust.org.in/activate-d-remit | https://npstrust.org.in/activate-d-remit, npstrust.org.in/activate-d-remit
  15 | npstrust.org.in/activate-tier-ii | https://npstrust.org.in/activate-tier-ii, npstrust.org.in/activate-tier-ii
  16 | npstrust.org.in/aif | https://npstrust.org.in/aif, npstrust.org.in/aif
  17 | npstrust.org.in/aif/about | https://npstrust.org.in/aif/about, npstrust.org.in/aif/about
  18 | npstrust.org.in/aif/aif-cell-careers | https://npstrust.org.in/aif/aif-cell-careers, npstrust.org.in/aif/aif-cell-careers
  19 | npstrust.org.in/aif/circular | https://npstrust.org.in/aif/circular, npstrust.org.in/aif/circular
  20 | npstrust.org.in/aif/coming-soon | https://npstrust.org.in/aif/coming-soon, npstrust.org.in/aif/coming-soon

  ... and 874 more (see JSON report).

- File targets with no match: **189**

  # | file target
  ------ | -----------
  1 | guidelines-for-operational-atal.pdf
  2 | Final_APY_FAQs_English_28-11-23.pdf
  3 | 02-FAQs-Ombudsman-under-APY.pdf
  4 | PFRDA+conducts+Atal+Pension+Yojana+Annual+Felicitation+Programme+on+20+May+2026+%28Wednesday%29+at+New+Delhi.pdf
  5 | Voluntary-Exit_APY-Withdrawal-Form.pdf
  6 | Scheme-Atal_Pension_Yojna_4.pdf
  7 | APY.pdf
  8 | CustomerGrievanceRedressal-CorporateBankIndiaDeutsheBank_AG_Oct2022.pdf
  9 | 23-Exit-FAQs-Corporate.pdf
  10 | 08-FAQs-for-Exit-from-National-Pension-System-by-citizens-including-corporate-sector-subscribers-0.pdf
  11 | 06-FAQs-for-Exit-from-National-Pension-System-by-citizens-including-corporate-sector-subscribers.pdf
  12 | 07-Corp-FAQ.pdf
  13 | PFRDA+Exits+and+Withdrawals+under+the+NPS+Regulations+2015+_Last+amended+on+20+July+2026_+%281%29.pdf
  14 | exits-and-withdrawals-under-the-national-pension-system-regulations-2015-last-amended-on-16-december-2025.pdf
  15 | GazettePFRDAExitandWithdrawalstheNPSAmendmentRegulations2025.pdf
  16 | Settlement_of_Corpus_Closure_Form_upd.pdf
  17 | Partial_Withdrawal_FAQs_0.pdf
  18 | reinvest.pdf
  19 | PFRDA+%28Exits+and+Withdrawals+under+the+National+Pension+System%29+%28Amendment%29+Regulations%2C+2026.pdf
  20 | AIS-Implementation-of-NPS-Rules-2026.pdf

  ... and 169 more (see JSON report).
