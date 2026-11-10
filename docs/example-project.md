# Itaconic-acid example

Open `/examples/itaconate` after starting the frontend. The example uses the real evidence-comparison and research-perspective components with a bundled snapshot. It makes no backend or model calls and cannot modify a project. Source expansion, paper filtering, result selection, and navigation between evidence, discussion, and overview remain interactive.

## Question and contents

For glucose-based itaconic acid production in *Yarrowia lipolytica*, should the first experiment modify the production pathway or change cultivation conditions?

The fixture contains 16 source passages, 29 extracted facts, six experiment records, two proposed actions, three role perspectives, and one review challenge. It contains no personal interviews, researcher accounts, confirmed decision rules, or invented local laboratory capabilities. No pending question is added merely to make the example look complete. Selecting a condition shows the interface used to contribute local context; saving is disabled in the example.

## Sources and attribution

- Jing Fu et al. (2024), *Reprogramming Yarrowia lipolytica metabolism for efficient synthesis of itaconic acid from flask to semipilot scale*, Science Advances 10, eadn0414. [Paper](https://doi.org/10.1126/sciadv.adn0414), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Cosetta Ciliberti et al. (2025), *Enhancing selective itaconic acid synthesis in Yarrowia lipolytica through targeted metabolite transport reprogramming*, Biotechnology for Biofuels and Bioproducts 18:65. [Paper](https://doi.org/10.1186/s13068-025-02668-9), [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/).

The quoted passages retain the saved source wording, PDF page numbers, and original-file hashes. Extracted plain text can contain PDF line-joining artifacts. Source passages remain distinct from the project’s interpretations; article material retains its own license. Full PDFs are not bundled.

## How the snapshot was prepared

The September 2026 walkthrough initially exposed retrieval, extraction, and linking errors. The comparison was then corrected against original PDFs, and model perspectives were edited and source-reviewed by the assistant. These saved reviewed outputs demonstrate the interface, not the accuracy of an untouched automatic run.

The public snapshot comes from `artifacts/itaconate-workflow/reviewed-perspectives.json` in the research archive. Export removes researcher posts and comparisons, repeated full first-page context, and the local workspace identity. Scientific passages, facts, experimental records, proposals, and reviewed discussion are retained. The export manifest records the source hash.

The comparison keeps flask and controlled-bioreactor experiments separate. For example, Ciliberti’s 19.66 g/L flask result is not interchangeable with 55.08 g/L on glucose or 37.71 g/L on glycerol in bioreactors. Fu’s Results and abstract report slightly different titers; the reviewed comparison uses the Results values and retains that discrepancy in the experiment notes. These records do not establish which intervention would work best in an unspecified laboratory.
