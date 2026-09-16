# Pre-delete report

- Generated: 2026-09-17T04:08:40
- Workbook: `/home/saksham/Downloads/nps_script/NPS_RAG_Ingestion_Review_TRIAGED.xlsx`
- URL sheet: `DROP - URLs` | file sheet: `DROP - Documents`
- Delete mode: `soft` | DRY_RUN: `True`

## Workbook targets

- URL rows in sheet: `822` (skipped empty: `0`, header-artifact rows ignored: `1`)
- URL target values: `1643` (distinct normalized: `894`) [example_url=822, canonical=821]
- File rows in sheet: `189` (skipped empty: `0`)
- File target values: `189`

## Detected in database

- URL documents matched: **2353**
- DOCUMENT rows matched: **461**
- Total documents to remove (after expansion): **2814** (expanded via supersedes/children: **0**)
- Attached chunks: total **43790**, active **43790**

### Breakdown by status / source type (matched rows)

  status | count
  ------ | ------
  COMPLETED | 2043
  ERROR | 765
  PROCESSING | 6

Matched rows by source type: DOCUMENT=461, URL=2353

Rows that are parent docs: `19` | rows superseded at match time: `517`

## Targets with no database match (informational)

- URL targets with no match: **90**

  # | normalized target | source values
  ------ | ----------------- | -------------
  1 | 56677 | 56677
  2 | pensionsahayak.pfrda.org.in/auth | pensionsahayak.pfrda.org.in/auth
  3 | pfrda.org.in/about-us/authority | pfrda.org.in/about-us/authority
  4 | pfrda.org.in/coming-soon | pfrda.org.in/coming-soon
  5 | pfrda.org.in/d/102654-lic-booklet-design-for-finance-ministry_sept-2025_eng-07-10-25 | pfrda.org.in/d/102654-lic-booklet-design-for-finance-ministry_sept-2025_eng-07-10-25
  6 | pfrda.org.in/d/102654-lic-booklet-design-for-finance-ministry_sept-2025_hindi-08-10-2- | pfrda.org.in/d/102654-lic-booklet-design-for-finance-ministry_sept-2025_hindi-08-10-2-
  7 | pfrda.org.in/d/11-empanelment-of-asp-application-form-1 | pfrda.org.in/d/11-empanelment-of-asp-application-form-1
  8 | pfrda.org.in/d/12-application-to-keep-empanelment-in-force-as-an-asp | pfrda.org.in/d/12-application-to-keep-empanelment-in-force-as-an-asp
  9 | pfrda.org.in/d/application-for-grant-of-certificate-of-registration-for-point-of-presence-atal-pension-yojana | pfrda.org.in/d/application-for-grant-of-certificate-of-registration-for-point-of-presence-atal-pension-yojana
  10 | pfrda.org.in/d/exit-govt-sector-model-cg-cab- | pfrda.org.in/d/exit-govt-sector-model-cg-cab-
  11 | pfrda.org.in/d/format-for-payment-of-renewal-fee | pfrda.org.in/d/format-for-payment-of-renewal-fee
  12 | pfrda.org.in/d/format-for-raising-appeal-to-ombudsman-for-resolution-of-grievances-under-national-pension-system-nps-atal-pension-yojana-apy- | pfrda.org.in/d/format-for-raising-appeal-to-ombudsman-for-resolution-of-grievances-under-national-pension-system-nps-atal-pension-yojana-apy-
  13 | pfrda.org.in/d/hindi-ra-individuals | pfrda.org.in/d/hindi-ra-individuals
  14 | pfrda.org.in/d/june-1st-2018-circular-superannuation | pfrda.org.in/d/june-1st-2018-circular-superannuation
  15 | pfrda.org.in/d/pfrda/12-application-to-keep-empanelment-in-force-as-an-asp | pfrda.org.in/d/pfrda/12-application-to-keep-empanelment-in-force-as-an-asp
  16 | pfrda.org.in/d/pfrda_staff-list | pfrda.org.in/d/pfrda_staff-list
  17 | pfrda.org.in/d/policy-for-bulk-transfer-of-self-managed-superannuation-fund-to-nps | pfrda.org.in/d/policy-for-bulk-transfer-of-self-managed-superannuation-fund-to-nps
  18 | pfrda.org.in/d/pop-nps-lite-spcpa-refund-process-and-claim-format-hindi-and-english | pfrda.org.in/d/pop-nps-lite-spcpa-refund-process-and-claim-format-hindi-and-english
  19 | pfrda.org.in/d/process-of-refund-from-subscribers-pension-contribution-protection-account-spcpa- | pfrda.org.in/d/process-of-refund-from-subscribers-pension-contribution-protection-account-spcpa-
  20 | pfrda.org.in/d/relevant-information-under-section-4-1-b-rti-act | pfrda.org.in/d/relevant-information-under-section-4-1-b-rti-act

  ... and 70 more (see JSON report).

- File targets with no match: **0**
