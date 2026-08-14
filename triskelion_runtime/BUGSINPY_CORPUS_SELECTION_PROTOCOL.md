# Checkpoint 3 BugsInPy corpus-selection lock

This selection protocol is frozen before checking out or inspecting any candidate source body.

- Upstream: `soarsmu/BugsInPy` at `11c5f1eea954a42132cfd06bf257766a7963e0fd`.
- Seed: `20260819`.
- All 17 projects are hash ordered. The first five projects form acquisition; the remaining twelve are protected and source-distinct by repository.
- Every bug within a project is hash ordered. Qualification tries candidates in that order without semantic skipping.
- A candidate qualifies only when its exact fixed commit provisions and passes the relevant tests while its buggy commit provisions and fails them.
- Checkout, dependency, interpreter, network, and timeout failures are infrastructure negatives. They are retained and cause progression to the next frozen candidate, never relabelling as scientific failure.
- Candidate source is not inspected until the project has one qualified bug and the acquisition/protected split is already fixed.
- Each attempt uses a disposable checkout. Harness files are kept outside the checkout so reset/clean cannot delete them.

Checkpoint 2's 35 QuixBugs tasks are now a development/regression suite, not an untouched confirmation set. Checkpoint 3's twelve protected repositories are the next unbiased competence gate.
