# Contributing

Thanks for your interest in improving Whitelistarr. This guide covers local
setup, the development workflow, and how releases are cut.

## Development setup

Requires Python 3.11 or 3.12.

```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows; use "source .venv/bin/activate" on Unix
pip install -e ".[dev]"
pytest         # run the suite
ruff check .   # lint
```

Optionally enable the pre-commit hooks (ruff + basic file checks):

```bash
pip install pre-commit
pre-commit install
```

## Workflow

1. **Branch off `main`:** `git checkout main && git pull && git checkout -b feat/short-name`.
2. **Write a failing test first.** The codebase is test-driven: pure logic gets
   direct unit tests, HTTP clients are tested with `respx` mocks, and Plex is
   tested via a fake video object — tests never hit a live server.
3. **Implement, then make the suite green.** `pytest` and `ruff check .` must pass.
4. **Open a pull request into `main`.** CI runs tests (Python 3.11 + 3.12), lint,
   CodeQL, a dependency audit, and — when the image changes — a Trivy scan.

Injected dependencies (clients passed into orchestrators) and managed-label
safety (only labels in `TAG_LABEL_MAP` are ever added or removed) are
load-bearing design rules — keep them intact.

## Commit and PR conventions

Commits and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/).
The type drives the automated version bump, so it matters:

| Type | Effect |
|---|---|
| `feat:` | minor release |
| `fix:` | patch release |
| `feat!:` or `BREAKING CHANGE:` | major release |
| `docs:` / `chore:` / `test:` / `ci:` / `refactor:` | no release |

Pull requests are squash-merged, so the **PR title** becomes the commit that
[python-semantic-release](https://python-semantic-release.readthedocs.io/) reads.
A non-conventional title means no release is cut.

Do not hand-edit the version in `pyproject.toml` or `app/__init__.py` — CI owns it.

## Releases

The project is **trunk-based**: `main` is the only permanent branch and releases
are fully automated.

- Each squash-merge to **`main`** cuts a stable release (GitHub Release +
  changelog) and publishes the image tagged `:latest` and `:X.Y.Z`.
- To stage a risky change before release, create a short-lived **`beta`** branch
  and push to it: it cuts prereleases (`vX.Y.Z-beta.N`) and publishes `:beta`.
  Open a PR from `beta` into `main`, merge, then delete `beta`.

Workflow: feature branch → PR into `main` → squash-merge. No long-lived `dev`
branch is needed.

## Reporting issues

- **Bugs and features:** use the issue templates.
- **Security vulnerabilities:** do not open a public issue. Follow
  [SECURITY.md](SECURITY.md) and use GitHub's private vulnerability reporting.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
