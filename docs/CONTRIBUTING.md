# Contributing

Use the [Engineering Toolkit](ENGINEERING_TOOLKIT.md) for supported trace,
replay, camera, and latency workflows from a release archive. Use a complete
Git checkout for source changes, tests, documentation generation, deployment,
and release packaging.

Thank you for helping improve VirtualGlove. Keep changes focused, readable,
and safe for a project that combines camera input, local networking, virtual
Linux devices, and a privileged shutdown helper.

User-facing documentation calls the Arduino UNO Q device the **VirtualGlove
Controller**. Introduce the hardware relationship once where it helps, then use
the product name. Preserve literal compatibility commands, filenames, installed
paths, service names, host placeholders, and hardware-specific statements.
References to Nintendo's original **Power Glove**, Super Glove Ball's emulated
controller, and the separately named `lr-nestopia-powerglove` core are factual
component names rather than VirtualGlove branding and must remain accurate.

## Before changing code

1. Start from the current `dev` branch and create a short-lived topic branch.
2. Read `SECURITY.md` before changing pairing, tokens, network listeners, downloads, file permissions, uinput, or shutdown behaviour.
3. Check `CONFIGURATION_REFERENCE.md` before changing a file format, default, installed path, port, controller mapping, or service unit.
4. Never commit `data/`, tokens, passwords, pairing codes, model caches and other runtime caches, or locally generated App Lab installation ZIP files.

Report security vulnerabilities through the private process described in
`SECURITY.md`. Do not disclose them in an ordinary pull request or public issue.

## Branch and release workflow

`dev` is the integration branch for ordinary development. Create feature, fix,
and documentation branches from the current `dev` branch, then open pull requests back to
`dev`. Do not commit ordinary development directly to `main`.

`main` represents released code. To prepare a release:

1. Confirm the complete quality workflow passes on `dev`.
2. Finalize the version and move the release notes out of `Unreleased`.
3. Open and review a pull request from `dev` to `main`.
4. Merge only the reviewed release changes, tag the release, and verify its generated App Lab package.
5. Merge any release-only adjustments on `main` back into `dev` immediately.

For an urgent released-version fix, branch from `main`, review and merge the
fix into `main`, publish the corrective release, and then merge `main` back into
`dev`. Keep both branches protected against unreviewed or failing changes when
the repository host supports branch protection.

## Guide layout and audience

Write the installation guide, gameplay guide, camera guide, troubleshooting guide,
quick reference, and other user manuals for someone downloading VirtualGlove
for the first time. Do not assume that reader has the project's camera, network
names, calibration, saved players, or development devices. Lead them from a fresh
installation through ordinary use, backups, maintenance, updates, and recovery.
Label tested hardware as a recommendation or example rather than presenting it as
the reader's configuration.

Keep user guides focused on what people see and what they should do. Put timing,
rendering, protocol, benchmark history, and other implementation details in the
technical references. Technical guides may describe the project's current UNO Q,
supported console, tests, successful experiments, and rejected approaches when that
evidence helps another developer reproduce or understand the result. Date or
otherwise qualify measurements that may change.
Use small contextual images in tables, place related images side by side, and
avoid repeating large images when a nearby table already identifies the display.
Keep headings, images, and captions together where practical when checking PDFs.

## Source style and documentation

Every project-authored executable script, source file, service unit, and
application configuration file that supports comments must begin with the
standard project header. Preserve a shebang
as the first line when one is required. The header must identify:

- project and repository-relative filename;
- concise purpose;
- author and copyright;
- `SPDX-License-Identifier: MIT`;
- a short dated change log;
- `docs/CHANGELOG.md` and Git as the complete history.

Imported or modified third-party source is the exception: retain its original
header, authorship, copyright, and license language verbatim. Do not replace or
prepend those notices with the VirtualGlove header. Keep project changes
in a separate patch and an additive component change ledger, and install or
distribute that ledger with the upstream license and notices. If a vendor source
tree is accepted later, place it under `third_party/` or `vendor/`; the source
audit deliberately exempts those paths from project-header requirements.

Python modules need a useful module docstring. Public classes and functions,
plus non-obvious security, protocol, lifecycle, and numerical helpers, need
focused docstrings describing their behaviour and safety conditions. Comments
should explain decisions and constraints rather than repeat the next line of
code.

Use four-space Python indentation, type annotations for interfaces, descriptive
names, bounded network and file operations, and existing project patterns.
Shell scripts use the shell declared by their shebang; Bash scripts should keep
`set -euo pipefail`. Avoid adding a dependency when the standard library or an
existing dependency handles the requirement clearly.

JSON does not accept comments. Keep JSON files valid and document their fields,
consumer, installed location, defaults, and secret status in
`CONFIGURATION_REFERENCE.md`.

Run the source audit before committing:

```sh
scripts/check-source-docs.py
```

## Tests and checks

Run these commands from the repository root on your development computer.
The [command reference](CONFIGURATION_REFERENCE.md#command-line-reference) explains their options.

Core tests must remain independent of a physical camera, VirtualGlove Controller, and console:

```sh
python3 scripts/run-tests.py --setup
python3 scripts/run-tests.py
python3 -m compileall -q python scripts src tests
```

The first command creates `.venv-test` with the pinned NumPy and headless
OpenCV versions used by local image-array tests. Later runs reuse it. The test
runner checks those imports before discovery and prints one setup instruction
instead of running a dependency-incomplete suite.

Run the documentation and syntax checks:

```sh
scripts/check-documentation.py
for file in scripts/*.sh; do bash -n "$file"; done
for file in retropie/bin/* retropie/*.sh; do sh -n "$file"; done
```

Add or update tests when behaviour, validation, security boundaries, packet
formats, gesture mappings, configuration parsing, or recovery paths change.
Do not add tests that only repeat static configuration without protecting a
meaningful contract.

## Documentation changes

Use Canadian English throughout project-authored public prose, including the
application, Help, website, guides, and release notes. Prefer forms such as
`behaviour`, `colour`, `centre`, `labour`, `recognise`, `customise`, `organise`,
and `personalise`. The user-facing action is **Centre hand**. Preserve exact
technical identifiers, protocol fields, command names, filenames, legal text,
and third-party product names when changing their spelling would break an
interface or misquote a source.

Use two spaces before top-level list markers and keep each item on one source
line. The current Help renderer treats wrapped continuation lines as separate
paragraphs. Leave blank lines before and after a list, and keep code examples
in fenced blocks outside the list. Rendered indentation and spacing are
controlled separately by the Help styles and PDF builder; inspect both when
publishing a documentation update.

Store project Markdown files under `docs/`, except for `README.md` in the
repository root. Write explanatory text in complete sentences and connected
paragraphs. Use lists for steps or related items and keep table labels concise.
Define unfamiliar terms when they first appear, use consistent names for
controls, and check grammar and punctuation before submitting changes.
Update all affected guides when a user-visible command, path, control, screen,
configuration field, dependency, or troubleshooting procedure changes.

### Screenshots, illustrations, and web artwork

Refresh application screenshots from the repository root with:

```sh
PYTHONPATH=src python scripts/capture-guide-screenshots.py
```

The development environment needs Playwright and Chrome. The script renders the
current application templates against isolated sample responses and temporary
player state. It never contacts a live Controller or console. Camera areas use
a labelled placeholder and pairing inputs use non-secret examples. The capture
covers Dashboard, Play, Academy learning and personalisation, player settings
and restoration, Setup, Games, Help, attract settings, and every guided-pairing
state. Shared filenames mean one refresh can affect several guides, so inspect
the images before rebuilding the PDFs. The script also checks the Security
network table at phone, tablet, and desktop widths.

Gesture artwork, architecture illustrations, and physical matrix photographs
are maintained separately. Preserve the intentional extra-finger artwork.
Generate compact Help copies with `scripts/build-help-images.py` after editing
the originals under `docs/images/gestures`. Individual web gestures are limited
to 320 pixels on their longest side and multi-gesture sheets to 960 pixels;
aspect ratio and transparency remain intact. PDF generation continues to use
the full-resolution originals.

Website branding icons live under `assets/`, not in the generated gesture
thumbnail directory. The shared shell uses `favicon.ico` and the Apple touch
icon; PNG variants remain available. Keep the original full logo unchanged.
Artwork origins, licensing, and screenshot provenance belong in the consolidated
[Third-party notices](../THIRD_PARTY_NOTICES.md#documentation-and-website-assets).

### Write for the reader's next action

1. Give each guide a clear job: the overview explains the project, installation leads to a working system, reference material defines settings and flags, and game cards help people play. Link between them instead of repeating long explanations.
2. Start a procedure with its goal, prerequisites, and the machine on which it runs. Use numbered steps with direct verbs, then state what success looks like and where to recover from a failure.
3. Explain every command's flags, required values, defaults, and effects in the command reference. Keep copyable examples free of terminal prompts and secrets.
4. Write complete sentences in explanatory paragraphs. Keep labels short, define unfamiliar terms, and remove filler, repeated cautions, and implementation details that do not help the reader act.
5. Give each game card an objective, a gesture-to-control table, and a small first-round exercise. Use light, specific encouragement; keep essential controls easy to find.
6. Check links, images, list numbering, and grammar. Follow each installation from an empty checkout on paper, and distinguish code review, automated checks, and actual fresh-device testing.

These conventions adapt [Microsoft's procedure guidance](https://learn.microsoft.com/en-us/style-guide/procedures-instructions/writing-step-by-step-instructions),
[Diátaxis's documentation types](https://diataxis.fr/), and
[Google's guidance on clear, conversational tone](https://developers.google.com/style/tone).
The game-card format also takes inspiration from
[Nintendo's beginner game tips](https://play.nintendo.com/news-tips/tips-tricks/super-smash-bros-ultimate-beginner-strategies/):
introduce the goal, connect a control to its result, and give the player
something manageable to try.

Describe changes that affect users in the appropriate category under `Unreleased` in
`docs/CHANGELOG.md`. Git history remains the exact implementation record; do
not paste a full Git log into individual source headers.

Review and revise the Markdown first. Keep PDF generation separate from the
editorial drafting cycle; regenerate the editions when the documentation is
approved for publication:

```sh
python3 scripts/build-docs-pdf.py
python3 scripts/build-enclosure-packages.py
python3 website/build.py
scripts/check-documentation.py --require-pdfs
```

When the interface changes, refresh the affected screenshots in `docs/images/`.
The repeatable full capture uses the current page templates, isolated sample data,
and an omitted-camera placeholder; it does not contact either device:

```sh
PYTHONPATH=src python scripts/capture-guide-screenshots.py
```

Install Playwright and Chrome in your development environment before running it.
The script also refreshes guided-pairing screenshots and checks the Security
network table at phone, tablet, and desktop widths.
Capture Dashboard, Play, Glove Academy practice, Glove Academy tuning, Setup, the Games section, and Help
from the running application. Blur the entire camera image before saving a
screenshot, keeping instructions and controls readable. Check that no passwords,
pairing codes, tokens, or identifying camera details remain. Do not commit
unblurred originals. Update image captions and inspect the corresponding PDFs.

Treat Markdown as the documentation source of truth. For publication, commit
the approved Markdown and matching regenerated PDFs together.
Treat `website/src/` as the website source of truth. Do not edit `website/dist/`
or the upload ZIP independently; rebuild them with `website/build.py` so the
release label, documentation ref, installer commands, and internal links remain
consistent with `config/release.json`.
Inspect the affected PDF pages for clipped text, broken tables, missing images,
and unintended page breaks before committing.

The public `README.md`, guides under `docs/`, and documentation images also
drive the Help Centre hosted by the VirtualGlove Controller. After a documentation change is
merged or otherwise ready to deploy, synchronize and verify that copy with:

```sh
scripts/deploy-uno-q-wifi.sh arduino@UNO-Q-NAME.local
```

That deployment restarts the VirtualGlove application and checks every
Help route, every public PDF, and representative gesture artwork. Confirm the
affected page and its **Open PDF** link in a browser after deployment. The
cabinet-specific `docs/cheatsheet.md` and its quick-reference PDF are
intentionally excluded from the public VirtualGlove Controller Help deployment. If the VirtualGlove Controller is
unavailable, state clearly that device synchronization and live Help
verification remain outstanding.

## App Lab installation package changes

Build and verify the model-bundled App Lab installation ZIP with:

```sh
scripts/build-app-lab-package.sh
scripts/verify-app-lab-package.py
```

The ordinary App Lab installation ZIP must contain production source,
configuration examples, documentation, the allowlisted public PDF guides, and the
required custom Linux ARM64 MediaPipe wheel used by the Controller, verified Google model, Apache 2.0 license,
and third-party notices. It retains the calibration and maintenance support tools
outside the engineering inventory in `scripts/package-inventory.py`, but excludes
that engineering inventory as well as private `data/`, tests, the cabinet
quick-reference PDF, caches, and Git history. Development deployments use
`--include-engineering`.

Build the optional version-matched research archive with
`scripts/build-engineering-tools-package.py --version VERSION`. The normal
release builder creates it alongside the two installers. Do not force-add generated
ZIPs to Git. GitHub Actions publishes a
short-lived verified ZIP artifact for each successful workflow run; tagged
releases may attach a verified ZIP for long-term distribution.

## Commits and pull requests

- Use a short imperative commit subject that describes the outcome.
- Explain what changed, why it was needed, and how it was verified.
- Keep unrelated cleanup separate from behavioural changes.
- Call out migration, deployment, compatibility, security, and rollback risks.
- Do not claim hardware verification unless the change was tested on the named device. Automated tests and simulated input should be described accurately.
- Wait for the GitHub Actions quality workflow to pass before merging.
- Target ordinary pull requests at `dev`; reserve pull requests into `main` for reviewed releases and urgent release fixes.

## Gesture tuning and firmware validation

Keep Glove Academy and gameplay on the same threshold checks and activation/release
states. Preserve the deliberate menu hold and game-specific pulses/toggles. Use
**Glove Zap** and **Pull Back** consistently in user-facing labels. Glove Academy and Tune
share the scanning-letter matrix renderer and its 160-millisecond frame timing.

Before releasing recognition changes, validate three-step hand setup and
individual tuning, including users who skip setup. Exercise V-sign and thumbs-up
with different curl ranges, incorrect extended fingers, and incomplete releases.
Verify neutral calibration ignores undetected, incomplete-scale, and sub-70%
confidence observations; requires 24 accepted frames in production; preserves
the previous saved reference until atomic completion; and reproduces a close,
not necessarily identical, result for the same simulated stance.
Check insufficient samples, tracking loss, overlapping ranges, and calibration
changes. Verify preview expiry, save/reload, selected-component reset, rejection
of unsupported stored formats without mutation, isolated player settings and progress,
stale-tab rejection after player changes or progress resets, and controller
suppression throughout tuning. Check that player selection automatically restores that player’s saved centre,
missing centres require centring, and hand-setting imports retain explicit calibration reuse;
Start controller remains required. Verify version-4 VirtualGlove round trips and
rejection of every older portable format without mutation,
invalid calibration rejection, and restart recovery between both restore writes. Automatic
suggestions must check separation and a simultaneous full-pose match in at least
90% of accepted samples in each phase, using candidate values and existing
personal extension thresholds. Test each extended finger, exact threshold
boundaries, default/personal ranges, tolerated noise, and failures occurring in
different frames. Failed analysis must clear previews without changing saved
settings. Extended-only samples still cannot learn a curled boundary. Manual
numerical editing and live-camera validation remain separate concerns.

Perform live camera checks of both menu poses, ordinary finger controls, Glove
Zap, Pull Back, and actual game input before release. Successful automated tests,
compilation, firmware upload, and bridge calls do not establish real-world
recognition quality or visually confirm the physical matrix animation.

Use the complete pinned Zephyr 1.0.0 configuration for compile-only validation,
then explicitly upload through App Lab. See the installation guide's
[firmware workflow](CONFIGURATION_REFERENCE.md#build-and-install-matrix-firmware).
Regenerate all PDF editions after documentation updates. Keep reference screenshots aligned with the current labels and layout. Use the
isolated capture workflow, or blur live camera imagery before taking a screenshot.


## Two-machine installer releases

Use [Build and publish installation assets](CONFIGURATION_REFERENCE.md#build-and-publish-installation-assets)
to package an explicit release tag. Both installers share `setup-machine.py` and
`install-package.py`; changes to host integration must cover first installation,
repeat updates, private-settings preservation, and read-only checks. Run
`test_install_packages.py` and `test_setup_machine.py`, plus the full test suite.
Keep development builds as prereleases. Workflow artifacts are not published
release downloads. Physical fresh-device and upgrade tests, cold boot, pairing,
and gameplay remain release gates; simulated filesystem tests do not replace them.

## Review parking lot

The Changelog records completed reviews and release evidence. Keep unresolved
measurement-dependent movement work here rather than maintaining a second
release history. Separate camera-to-display validation from routine UI and
persistence fixes.
