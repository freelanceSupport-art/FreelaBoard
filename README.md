# FreelaBoard

FreelaBoard is a local-first Windows desktop app for freelancers who want to manage projects, deadlines, invoices, payments, and CSV exports without signing up for a cloud service.

![FreelaBoard icon](assets/brand/Icon.png)

## What It Helps With

- Track freelance projects from inquiry to completion
- See upcoming and overdue deadlines at a glance
- Manage invoice and payment status locally
- Export the current project list to CSV
- Stay notified from the Windows notification area
- Keep working from a single portable EXE

## Highlights

- Local SQLite storage
- Deadline alerts with on/off switching
- Optional resident mode when the window is closed
- Notification-area right-click menu: open panel or exit
- Futuristic dark GUI for project operations
- Single-file Windows EXE build with PyInstaller
- Source icon and generated Windows icon assets separated for clean branding

## Download

The Windows executable is built as:

```text
dist\FreelaBoard.exe
```

For GitHub publication, attach the built EXE to a GitHub Release instead of committing `dist/` to the repository.

## Run From Source

```powershell
python main.py
```

## Build The EXE

```powershell
.\build_exe.ps1
```

The build script converts `assets\brand\Icon.png` into generated app icons and embeds the `.ico` file into the EXE.

## Repository Layout

```text
src/freelaboard_app/       Application code
tests/                     SQLite and notification-target tests
assets/brand/              Source branding assets
assets/generated/          Generated icon files used by the app/build
docs/marketing/            Landing-page copy, ad copy, and release notes
docs/PUBLISHING_CHECKLIST.md
.github/                   CI workflow and GitHub templates
scripts/                   Maintenance helpers
tools/                     Build-time asset tools
main.py                    Thin launcher
build_exe.ps1              Single-EXE build script
```

## GitHub Repository

Target repository:

[freelanceSupport-art/FreelaBoard](https://github.com/freelanceSupport-art/FreelaBoard)

## Current Release Message

FreelaBoard helps freelancers manage projects, deadlines, billing status, and payment status in one local Windows tool. It is designed for people who want a practical desktop cockpit instead of a cloud subscription.

## License

FreelaBoard is released under the MIT License. See [LICENSE](LICENSE).
