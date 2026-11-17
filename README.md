# wwl2755.github.io

Source for my blog. GitHub Pages serves the built site from `docs/` on `main`.

## Write a post

1. Add `content/posts/YYYY-MM-DD-slug.md` with front matter:

   ```
   ---
   title: My post
   date: 2026-11-16
   description: One line for the post list and link previews.
   ---
   ```

2. Figures: add a generator to `tools/figures.py` (SVG, colours from the CSS variables so they follow light and dark mode), then put `{{fig:name|caption}}` on its own line in the post.
3. Build and commit the output:

   ```bash
   pip install markdown pygments
   python3 tools/figures.py   # only when figures change
   python3 tools/build.py     # writes docs/
   ```

Preview locally with `python3 -m http.server -d docs 8000`.
