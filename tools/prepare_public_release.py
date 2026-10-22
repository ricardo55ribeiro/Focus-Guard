"""Export only reviewed source files, never private runtime data or Git history.

Run from any directory: python tools/prepare_public_release.py DESTINATION
The destination must not exist. This tool never publishes or rewrites history.
"""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    ".gitignore", ".gitattributes", "LICENSE", "README.md", "Privacy Policy.txt",
    "SECURITY.md", "CONTRIBUTING.md", "THIRD_PARTY.md", "requirements.txt",
    "settings.example.json", "install.py", "install.bat", "create_shortcut.bat",
    "create_shortcut.ps1", "launch_focusguard.vbs",
)
PATTERNS = {
    "agent": ("*.py", "*.pyw"),
    "extension": ("*.js", "*.html"),
    "tests": ("*.py", "*.js"),
    "tools": ("*.py",),
    ".github": ("*.yml", "*.md"),
}
EXTRA_FILES = (
    "agent/icon.ico", "extension/manifest.json",
    "extension/icons/icon48.png", "extension/icons/icon128.png",
)


def source_files(root: Path):
    paths = {root / name for name in (*ROOT_FILES, *EXTRA_FILES)}
    for directory, patterns in PATTERNS.items():
        for pattern in patterns:
            paths.update((root / directory).rglob(pattern))
    for path in sorted(paths):
        relative = path.relative_to(root)
        if any(part in {"logs", "debug", "config", "__pycache__"} for part in relative.parts):
            continue
        if any(parent.is_symlink() or getattr(parent, "is_junction", lambda: False)()
               for parent in (path, *path.parents) if parent != root.parent):
            raise ValueError(f"Refusing link/junction: {relative}")
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Missing or unsafe source file: {relative}")
        yield path, relative


def export(destination: Path, root: Path = ROOT) -> int:
    destination = destination.absolute()
    if destination.exists():
        raise ValueError("Destination already exists; choose a new directory.")
    files = list(source_files(root))
    destination.mkdir(parents=True, exist_ok=False)
    for source, relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count = export(args.destination)
    print(f"Exported {count} source files to {args.destination.absolute()}")
    print("Review the export, then initialize a NEW Git repository there.")


if __name__ == "__main__":
    main()
