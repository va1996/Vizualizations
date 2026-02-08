# CLAUDE.md

## Project Overview

**Vizualizations** is a collection of interactive scientific visualization dashboards deployed as static web pages. The current primary visualization is an **Interactive 3D Bisphenol Angles** viewer that renders molecular structures of bisphenol compounds (BPT, BPA, BPF) with real crystallographic data from Lim & Tanski (2007).

**Author:** Vanessa Srebny (va1996)
**License:** MIT

## Repository Structure

```
Vizualizations/
├── .github/
│   └── workflows/
│       └── static.yml      # GitHub Pages deployment workflow
├── docs/
│   ├── index.html          # Main application (single-file SPA, ~1220 lines)
│   └── Read.me             # Placeholder
├── CLAUDE.md               # This file
├── LICENSE                  # MIT License
└── README.md               # Project description
```

## Tech Stack

- **Frontend:** Vanilla HTML/CSS/JavaScript (no framework, no build tools)
- **3D Rendering:** Three.js r128 (loaded via CDN)
- **Deployment:** GitHub Pages via GitHub Actions
- **Dependencies:** Zero npm dependencies; fully self-contained

There is no `package.json`, no bundler, no linter, and no test framework. The entire application lives in a single HTML file with embedded CSS and JavaScript.

## Development Workflow

### Local Development

1. Open `docs/index.html` directly in a browser, or serve via any static file server
2. No build step required - edit the HTML file and refresh the browser
3. All CSS is embedded in `<style>` tags; all JS is embedded in `<script>` tags

### Deployment

Deployment is automatic via GitHub Actions (`.github/workflows/static.yml`):
- **Trigger:** Push to `main` branch or manual workflow dispatch
- **Target:** GitHub Pages
- **Process:** Uploads the entire repository as a static site artifact
- The served content comes from the `docs/` directory (GitHub Pages configuration)

### Git Conventions

- The `main` branch is the production branch
- Feature branches use the pattern `claude/<description>-<id>`
- Commit messages are short and descriptive

## Architecture

### Single-File SPA Pattern

The application (`docs/index.html`) follows a single-file architecture:

1. **CSS** (~370 lines) - Embedded in `<style>`, uses CSS Grid, Flexbox, media queries
2. **HTML** (~250 lines) - Semantic markup with controls, dual canvas viewers, info panels
3. **JavaScript** (~600 lines) - Embedded in `<script>`, manages Two Three.js scenes

### JavaScript Organization

The JS code follows a module-by-function pattern with global state:

```
Global State Variables (scene, camera, renderer, molecule, currentCompound, etc.)
│
├── initMain()              # Initialize the main 3D molecular viewer
├── initAngle()             # Initialize the angle visualization viewer
├── createMolecule()        # Build 3D molecular geometry from compound data
├── createPhenylRing()      # Generate hexagonal phenyl ring geometry
├── createAngleVisualization()  # Build angle reference visualization
├── setupMouseControls()    # Drag-rotate and scroll-zoom handlers
├── updateAngleInfo()       # Update UI with current compound parameters
├── animate()               # requestAnimationFrame loop for both scenes
│
├── Event listeners          # Compound/view selector change handlers
└── Initialization calls     # initMain(), initAngle(), animate()
```

### Data Model

Compound data is stored in a `compounds` object with keys `BPT`, `BPA`, `BPF`. Each entry contains:
- `name`, `bridgeAngle`, `bondLength`, `dihedralAngle`, `pitchAngles`
- `bridgeAtom` (S or C), `bridgeColor`, `color`
- Optional: `hasMethyl` (BPA only)

### 3D Scene Structure

Two side-by-side Three.js canvases:
- **Left (Main Viewer):** Full 3D molecular structure with phenyl rings, bridge atom, bonds, and optional reference plane
- **Right (Angle Viewer):** Abstract angle visualization showing bridge angle (red), pitch angles (green), and dihedral angle (blue)

Both support mouse-drag rotation and scroll zoom.

## Coding Conventions

### JavaScript
- `camelCase` for variables and functions
- Three.js objects use their standard `PascalCase` constructors
- Angle math uses radians internally, degrees in the UI and data model
- Comments mark major sections and explain non-obvious geometry calculations
- No error handling (assumes valid inputs from controlled dropdowns)
- No modules/imports - everything is in global scope

### CSS
- BEM-like class naming: `.control-group`, `.viewer-container`, `.info-panel`
- Color palette: blues (`#1e3c72`, `#2a5298`), red (`#e74c3c`), green (`#2ecc71`), orange (`#f39c12`), light blue (`#3498db`)
- Responsive breakpoint at 968px (stacks grid to single column)
- Consistent spacing: 15px, 20px, 25px, 30px increments
- Smooth transitions (`transition: all 0.3s`) and box shadows for depth

### HTML
- Semantic elements with proper heading hierarchy
- Labeled form controls for accessibility
- Tables with `thead`/`tbody` for data display

## Guidelines for AI Assistants

1. **No build tools** - Do not introduce npm, webpack, or any build infrastructure unless explicitly requested. The project's simplicity is intentional.
2. **Single-file pattern** - The main application lives in `docs/index.html`. Keep CSS and JS embedded unless the user requests extraction.
3. **Scientific accuracy** - Molecular data comes from published crystallographic research. Do not modify compound parameters without a cited source.
4. **Three.js r128** - The project uses an older but stable Three.js release loaded via CDN. Do not upgrade without explicit request, as API changes may break the visualization.
5. **GitHub Pages deployment** - All served content must be in the `docs/` directory (or the repository root, depending on Pages config). New pages should go in `docs/`.
6. **No external dependencies** - Keep the project dependency-free unless the user requests additions.
7. **Preserve visual design** - The UI has a consistent professional color scheme and responsive layout. Maintain the existing design language when making changes.
8. **Test in browser** - Since there are no automated tests, changes should be verified by opening `docs/index.html` in a browser.
