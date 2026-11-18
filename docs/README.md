# Documentation

Start here to find a document. Each folder's README says what it holds and why.

| Folder or file | What it is |
|---|---|
| [settings/](settings/README.md) | **Settings development:** how defaults and the setup wizard's choices are decided, and the rules for changing them. |
| [testing/](testing/README.md) | **Testing development:** test material, where audio is kept (this PC only), voice service terms, and the synthetic voice plan. |
| [VALIDATION.md](VALIDATION.md) | Measuring accuracy on your own voice with an invented reading script. |
| [BENCHMARKS.md](BENCHMARKS.md) | Published results on every test set ([images](images/README.md)). |
| [optimization/](optimization/) | Each round of measurements and what was changed. |
| [overnight/](overnight/README.md) | Logs of unattended test runs. |
| [STRESS_TEST_PLAN_1060.md](STRESS_TEST_PLAN_1060.md) | Tests on 6 GB graphics cards. |
| [CPU_AND_OTHER_HARDWARE_PLAN.md](CPU_AND_OTHER_HARDWARE_PLAN.md) | Computers without an NVIDIA card. |
| [port-plan/](port-plan/) | The move to PyQt6. |
| [PROJECT_SOP.md](PROJECT_SOP.md) | How work on the project is run. |
| [archive/](archive/) | Superseded drafts. |

Other plans and trial notes sit at this level: MedASR, the personal curriculum, phone and
remote samples, and the original app.

## Branches

- **`dictation/personal-english`** is the development line. Every change lands here first.
- **`release/tester-preview`** is what testers get. It carries the same commits, copied one at
  a time, but leaves out the commercial dictation product the developer compared against: its
  replay script, its tests and comparisons that name it.
- **One commit per concern** (docs, a tool, a data set, an app change), each with its tests. A
  commit can then be reviewed, copied or reverted on its own.
- **Before a commit is pushed to either branch,** the tests pass on that branch. On the tester
  branch, a search for the product's name must also find nothing.

**Never in the repository:**
- recordings, synthetic audio and transcripts, which stay in `results_1060/` on the PC that
  made them;
- API keys, which stay in environment variables.
