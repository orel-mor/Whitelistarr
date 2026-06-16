## What & why

<!-- Briefly: what does this change and why? Link any issue (#123). -->

## Conventional Commit

<!--
The PR TITLE drives the release + changelog. It must start with one of:
  feat:  (minor)   fix: / perf:  (patch)   feat!: or BREAKING CHANGE: (major)
  docs: / ci: / build: / chore: / refactor: / test: / style:  (no release)
-->

## Checklist

- [ ] PR title is a Conventional Commit
- [ ] `pytest` passes and `ruff check .` is clean
- [ ] README / `.env.example` updated if config changed
- [ ] Considered `DRY_RUN` and managed-label safety if touching labels
