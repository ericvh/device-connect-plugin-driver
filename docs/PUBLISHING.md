# Publishing to PyPI

## One-time setup

1. Create a project on [PyPI](https://pypi.org/) named `device-connect-plugin-driver`.
2. Configure [trusted publishing](https://docs.pypi.org/trusted-publishers/) for the GitHub repo `ericvh/device-connect-plugin-driver` and workflow `publish.yml`.
3. Add a GitHub **environment** named `pypi` (Settings → Environments) if you want approval gates.

## Release flow

1. Bump `version` in `pyproject.toml` and update `CHANGELOG.md`.
2. Commit, tag, and push:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
3. Create a **GitHub Release** from the tag (or publish a draft release). The `Publish` workflow uploads the sdist/wheel to PyPI.

## Manual publish (fallback)

```bash
python -m pip install build twine
python -m build
twine upload dist/*
```

## Install

```bash
pip install device-connect-plugin-driver
pip install device-connect-plugin-driver[concentrator]
```
