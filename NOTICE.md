# Third-party data

## Medical term list (spelling correction)

`src/vocab/telnyx_medical_terms.txt` and `tests/data/whisper_misrecognitions.tsv`
are derived from the **Medical Pronunciation Dictionary** by Telnyx, Inc.
(https://github.com/team-telnyx/medical-pronunciation-dictionary), © 2026 Telnyx, Inc.,
licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).

Changes: kept only the term text and category (pronunciation fields dropped); the
test file keeps the term and the "heard_without_dict" transcription columns, split
into "fix" and "keep" regression cases.

## Curated primary-care vocabulary

`src/vocab/primary_care.txt` was written for MyTranscribe (MIT, same as the rest of
the repository). Coverage was guided by public sources (AHRQ MEPS-based prescription
rankings, CDC NAMCS primary-care visit diagnoses, CDC and NACI immunization
schedules); no lists were copied from them.
