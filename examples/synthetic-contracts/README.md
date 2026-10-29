# Synthetic demo inputs

These four files contain no real contracts or personal data. The target phrase and
expected outcomes are recorded in `manifest.json`. At Milestone 1 every upload is
**not processed**; expected search outcomes are acceptance targets for later work.

- A: digital PDF with the target phrase.
- D: digital PDF without the target phrase.
- P: a rasterized, clearly printed JPEG of A, requiring real OCR later.
- E: a degraded, rotated scan of D. Set **manual review required** when uploading.
  This is a difficult printed scan, not a handwriting-recognition benchmark.

Regenerate from the repository root after installing the backend dependencies:

```sh
.venv/bin/python scripts/generate_fixtures.py
```

The generator uses built-in PDF fonts, fixed content and a seeded degradation
process. Library versions are recorded in the manifest; different rasterizer or
JPEG versions can change bytes. Checked-in SHA-256 values describe the actual
checked-in files. Never substitute the expected outcomes for real extraction.
