# Codex-Project-Repo

A workspace for building projects with GitHub Copilot / Codex.

## Getting Started

1. **Clone the repo**
   ```bash
   git clone https://github.com/jordanar189/Codex-Project-Repo.git
   cd Codex-Project-Repo
   ```

2. **Create a feature branch for each project**
   ```bash
   git checkout -b my-new-project
   ```

3. **Start building** — add your source files under `src/` (or create a project-specific folder at the root).

## Repository Layout

```
Codex-Project-Repo/
├── src/            # Shared / starter source files
│   └── main.py     # Example Python entry point
├── .gitignore      # Common ignored files
└── README.md       # This file
```

## Tips for working with Codex

- Keep file sizes manageable — Codex works best with focused, single-purpose files.
- Use descriptive function and variable names; they act as in-line documentation for the model.
- Break large tasks into small, well-named functions and let Codex fill in the implementation.
- Commit often so you can easily compare AI-generated changes against your baseline.
