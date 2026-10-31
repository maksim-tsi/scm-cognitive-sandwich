# Publication-specific release preparation

These are release candidates for author review. This PR does not publish a final
GitHub release, create/move tags or merge itself. Existing studies and denominators
remain separate. Use the exact source commit in `prepared-manifest.json` once built.

```sh
python3.13 release-candidates/build.py --revision <source-commit> --output /tmp/scm-release-candidates
```

The builder reads only committed public Git objects. It includes one study and
the root license, rejects prohibited/sensitive material, fixes archive metadata,
uses uncompressed ZIP for cross-zlib byte stability, and checks every entry hash.
Rebuilding the same revision produces the same bytes. It never contacts a model,
private source, infrastructure service, or GitHub mutation endpoint.

| Proposed release | Scope |
| --- | --- |
| idwl-2026-v1 | Publication-specific navigation, citation and preserved public code source anchor. The candidate ZIP is not a self-contained executable legacy runtime. No new paper/code adjudication required. |
| maritime-extension-2026-v1 | Retained analysis, design inputs, source excerpts, prompts and recovered parsed responses. Execution input binding and raw response gaps remain explicit. |
| systems-urban-freight-2026-v1 | Existing unchanged Systems package: results reproduction and I2/I3 replay. Manuscript status until actual journal publication. |

Notes are in the three corresponding `.md` files. After separate author approval,
create immutable publication-specific tags/releases against the reviewed revision
and attach the checksummed candidate archives. Do not describe code fragments or
source-anchor navigation as a fully runnable historical experiment.
