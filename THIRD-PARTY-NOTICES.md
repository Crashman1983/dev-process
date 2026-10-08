# Third-party notices

This project's own license is `LICENSE` (Apache License 2.0).
The material below is incorporated from third parties under their own terms,
which continue to apply to those portions.

## GitHub Spec Kit (MIT)

The Spec Kit toolkit itself (`specify-cli`) is **not** bundled here — adopters
install it from PyPI, where it carries its own MIT license. However, two files
in this template are **derivative works** of Spec Kit's templates and retain
their structure and portions of their wording:

- `template/.specify/templates/overrides/spec-template.md`
  (derived from Spec Kit's `spec-template.md`)
- `template/.specify/templates/overrides/tasks-template.md`
  (derived from Spec Kit's `tasks-template.md`)

Upstream: <https://github.com/github/spec-kit>

```
MIT License

Copyright GitHub, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Matt Pocock — skills (MIT)

Three passages are adapted (paraphrased and condensed, not copied) from
Matt Pocock's agent skills, v1.3.1:

- the Debug method in `template/docs/process/workflow.md.jinja`
  (from `skills/engineering/diagnosing-bugs`)
- clarifying in rounds in the Brainstorm section of the same file
  (from `skills/productivity/grilling`)
- the tautological and internals-coupled tests in
  `template/docs/process/testing.md` (from `skills/engineering/tdd`)

Upstream: <https://github.com/mattpocock/skills>

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Anthropic — Claude Code official plugins (Apache License 2.0)

Two review rules are adapted (paraphrased) from the `code-review` and
`pr-review-toolkit` plugins of `anthropics/claude-plugins-official`, which are
licensed under the Apache License 2.0, the same license as this project:

- verifying each blocking finding with a scored, independent check
  (`template/docs/process/verification-independence.md`, "What blocks";
  the bundle preamble in `template/scripts/process/make_review_bundle.py`)
- the silent-failure walk in `template/docs/process/review-checklist.md`
  (from the `silent-failure-hunter` agent)

Upstream: <https://github.com/anthropics/claude-plugins-official>
