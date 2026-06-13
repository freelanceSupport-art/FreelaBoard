# Publishing Checklist

Use this before pushing FreelaBoard to GitHub or creating a public release.

## Repository

- Confirm remote repository: https://github.com/freelanceSupport-art/FreelaBoard
- Confirm the default branch is `main`.
- Confirm `LICENSE` is present and uses the MIT License.
- Keep `dist/`, `build/`, `.spec`, SQLite databases, and caches out of git.
- Commit `assets/brand/Icon.png` as the canonical brand asset.
- Commit `assets/generated/` icons when you want GitHub visitors to see the packaged branding assets.

## Release

- Run `python -m unittest discover -s tests`.
- Run `python -m compileall src main.py tools`.
- Run `.\build_exe.ps1`.
- Smoke-start `dist\FreelaBoard.exe`.
- Attach `dist\FreelaBoard.exe` to a GitHub Release.

## Marketing

- Use `docs/marketing/landing-copy.md` for product-page copy.
- Use `docs/marketing/social-posts.md` for short announcements.
- Use `docs/marketing/release-notes-v0.2.0.md` for the first release description.
- Add screenshots before advertising heavily.

## Open Decisions

- Decide whether releases should be versioned as `v0.2.0` or reset to `v0.1.0` for the first GitHub release.
- Decide where user support requests should go.
