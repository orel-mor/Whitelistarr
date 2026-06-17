## What & why

<!-- Briefly: what does this change and why? -->

<!-- To auto-close issues on merge, put a keyword before EACH number:
     "Closes #12, Closes #13"  (a comma list like "Closes #12, #13" closes only #12). -->
Closes #

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
