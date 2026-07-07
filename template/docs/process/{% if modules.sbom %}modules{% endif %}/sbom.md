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

Copy the shipped example to `docs/process/sbom-policy.json` and adjust:

- **`sbom_paths`** — globs locating the CycloneDX file(s). Default covers common
  names (`bom.json`, `**/*.cdx.json`, `sbom/*.json`).
- **`allowed_licenses`** — SPDX ids/expressions the project permits. Omit to only
  require that a license is *present* (no allow-list).
- **`manifest_paths`** — dependency manifests (`package.json`, `pom.xml`, …) for an
  advisory coverage check.
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
