# Stuart v1 — System dependencies

Stuart v1 is mostly Python, but a few features depend on native system packages.

## Required

### ffmpeg (required)
Used by the **normalize** stage to convert audio/video inputs into a canonical WAV.

Verify:
- `ffmpeg -version`

## Optional but strongly recommended

### WeasyPrint native deps (recommended for real PDFs)
If WeasyPrint is installed without the right OS libraries, PDF export will fail and Stuart will fall back to a stub PDF.

#### Ubuntu / Debian
```bash
sudo apt-get update
sudo apt-get install -y \
  ffmpeg \
  libcairo2 \
  libpango-1.0-0 \
  libpangoft2-1.0-0 \
  libgdk-pixbuf2.0-0 \
  libffi-dev \
  shared-mime-info \
  libharfbuzz0b \
  libfribidi0 \
  libjpeg-turbo8 \
  zlib1g
```

If you are on another distro, install equivalents for:
- Cairo
- Pango (+ harfbuzz/fribidi)
- gdk-pixbuf

#### macOS (Homebrew)
```bash
brew install ffmpeg cairo pango gdk-pixbuf libffi
```

#### Windows
Windows can work, but **native WeasyPrint deps are painful**.

Recommendation:
- Use **WSL2 Ubuntu** and follow the Ubuntu/Debian instructions above.
