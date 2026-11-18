# Benchmark images

Four images of the benchmark results, for the README, the benchmark page and for sharing.
Each is kept as an SVG (editable) and a PNG at twice the size (for posting).

| File | Size | Shows | Used in |
|---|---|---|---|
| `share_card` | 1200×630 (link-preview size) | Headline, the claim, tiles for 7.0% / 2.1% / 0 bytes, Whisper on its own vs the full build | Top of the README; social posts |
| `steps` | 1200×740 | "Half the word errors of Whisper on its own": Whisper as it comes, then each step the app adds, on Corti and the held-out recordings | README; BENCHMARKS.md, "What the pipeline adds" |
| `head_to_head` | 1200×790 | "The most accurate open model we tested": five systems on the same audio | README; BENCHMARKS.md, "Head to head" |
| `difficult_audio` | 1200×720 | "Holds up on difficult audio": clinical terms right by recording condition (Modulate) | BENCHMARKS.md, "Many voices, difficult audio" |

## Redrawing them

1. Change the figure in [`docs/BENCHMARKS.md`](../BENCHMARKS.md) first. It is the source of
   every number.
2. Change the same number in [`scripts/make_promo_images.py`](../../scripts/make_promo_images.py)
   (each image is one function; the numbers are written in it).
3. Run it from the repository folder with any Python 3 (no packages needed):

   ```
   python scripts/make_promo_images.py
   ```

   It writes the SVGs, then renders each PNG with Microsoft Edge in headless mode. Without
   Edge it writes the SVGs only.
4. Open every PNG and look at it before committing: text running into other text, a note
   crossing a bar or gridline, the footer touching the brand line. The script checks none of this.
5. Update any other place that quotes the same number: the README text, BENCHMARKS.md's
   "At a glance", the scorecard page.

## Rules the images follow

Keep to these when changing an image or adding one.

**Honest charts**
- Every axis starts at zero. Never trim an axis to make a gap look bigger.
- Every panel names its test set and how many notes or recordings it covers ("Corti
  Med-Dictate, 24 notes"). Every image has a source line saying when it was measured.
- Show results we lose as plainly as results we win. On Corti the commercial system is
  ahead (6.0% against 7.2%), and the head-to-head image shows that.
- When two images show different figures for the same thing, a footnote says why. The
  head-to-head uses the 23 Corti notes with a commercial capture and the November 15 runs
  (7.2%, 3.3%); the others use all 24 notes and today's build (7.0%, 2.9%).
- Synthetic voices (Modulate) are labelled as such: good for comparing conditions, not a
  measure of accuracy on real clinicians.

**Wording**
- No commercial product is named. Say "commercial cloud medical dictation" or
  "commercial-grade". This matters most on the tester branch, which carries no product names.
- The claim is always worded "word error rates similar to or better than commercial-grade
  medical dictation in our testing". Do not strengthen it.
- Corti is described as used for evaluation only.
- No recordings, transcripts, references or anything from `results_1060/` goes into an image.
  Only the summary figures already published in BENCHMARKS.md.

**Look**
- One idea per image, said in the title. The subtitle says what is measured and which way is
  better ("Word errors (lower is better)").
- Our build is the only coloured bar; everything else is grey, so the eye goes to one place.
  The commercial reference is a darker grey than the other open models.
- Thin bars (18–20 px) rounded only at the data end, hairline gridlines, plenty of space.
- Values are written at the end of each bar. Notes on a bar sit on a surface-coloured box so
  gridlines do not run through the text.
- One typeface (Segoe UI or the system sans) everywhere, including the big numbers.
- A legend whenever more than one colour carries meaning (the difficult-audio dot chart).

**Colours** (light background)

| Role | Hex |
|---|---|
| Background | `#fcfcfb` |
| Tile background | `#f4f3ef` |
| Main text | `#0b0b0b` |
| Secondary text | `#52514e` |
| Muted text, source lines | `#898781` |
| Gridlines | `#e1e0d9` |
| Zero line, axis | `#c3c2b7` |
| MyTranscribe Medical | `#2a78d6` (blue) |
| Commercial reference | `#898781` |
| Other systems | `#c9c7bd` |
| Three-series charts, in this order | `#2a78d6`, `#eb6834`, `#1baf7a` |

The three series colours were checked as a set to stay distinguishable for colour-blind
readers. Do not add a fourth colour to a chart that compares every series with every
other (dot charts, scatter). Fold extra systems into grey or make a second chart instead.
