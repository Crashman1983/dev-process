# Module: sbom

Opt-in. Requires a **Software Bill of Materials** (CycloneDX JSON) that attests a
**license for every third-party component**, and permits only the licenses the
project allows. When enabled it makes "third-party dependencies are inventoried
with an attested license" part of what *done* means — a new or changed dependency
updates the SBOM before merge.

## When required

Enable when third-party supply-chain transparency and license compliance are part
of "done" — most products shipping external dependencies.

## Policy

Copy the shipped `sbom-policy.example.json` to a policy file named
`sbom-policy.json` in the same folder, and adjust:

- **`sbom_paths`** — globs locating the CycloneDX file(s). Default covers common
  names (`bom.json`, `**/bom.json`, `**/*.cdx.json`, `sbom/*.json`).
- **`allowed_licenses`** — SPDX ids the project permits. A component's SPDX
  **expression** is evaluated against them (`A OR B` passes if either is allowed;
  `A AND B` requires both), and a component bound by several separate license
  entries must have every one allowed. Licenses attested by full **name**
  (`MIT License`) rather than SPDX id are matched verbatim — allow-list the id
  your SBOM actually emits. Omit `allowed_licenses` to only require that a license
  is *present* (no allow-list).
- **`manifest_paths`** — dependency manifests for the advisory coverage check.
  The check can parse `package.json` and `pom.xml` — only list what it reads.
  List each kind both bare and under `**/` (`"package.json", "**/package.json"`):
  a root-level manifest does not match the `**/` form, so a `**/`-only list
  silently skips the most common layout.
- **`exclude`** — component-name globs exempt from the checks (e.g. internal
  first-party modules the SBOM lists).

## The gate

`scripts/process/check_sbom.py` runs in `process-gates` (CI) and the pre-push hook.
It degrades like the other gates — advisory when data is absent, hard on a real
violation:

| Situation | Result |
| --------- | ------ |
| no `sbom-policy.json` | advisory note, pass |
| broken policy JSON | **fail** |
| policy present, no SBOM found | advisory note, pass (generate one) |
| a library component with no license | **fail** — attestation missing |
| a library license outside `allowed_licenses` | **fail** |
| a manifest dependency absent from the SBOM | advisory note (best-effort) |

Bypass with `SKIP_SBOM=1` (and say why in the commit — mandatory rule 8).

## Generating the SBOM

The gate *verifies* a committed CycloneDX SBOM; it does not generate one — that is
a build concern. Wire a generator into the build so the SBOM stays current, e.g.:

- **Maven** — the CycloneDX Maven plugin (`makeBom`) writes a CycloneDX `bom.json`
  into the build output; commit it (or a copy under an `sbom` folder).
- **npm** — `@cyclonedx/cyclonedx-npm --output-file bom.json`.
- **multi-ecosystem** — `syft <dir> -o cyclonedx-json` into a committed `bom.json`.

Keep the committed SBOM in step with the dependency manifests: a new or changed
dependency updates it before the change is done.
