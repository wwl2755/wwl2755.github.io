"""Build the static site into docs/ (GitHub Pages serves main:/docs).

    python3 tools/figures.py   # only when figures change
    python3 tools/build.py

Posts live in content/posts/YYYY-MM-DD-slug.md with a small front matter block.
A line {{fig:name|caption}} inlines assets/fig/name.svg as a captioned figure.
"""
import re
import shutil
from datetime import date
from html import escape
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
SITE = {"title": "Wenlong Wang", "author": "Wenlong Wang", "url": "https://wwl2755.github.io",
        "tagline": "I work on LLM inference systems."}


def front_matter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    return meta, text[m.end():]


def figures(body):
    def repl(m):
        name, caption = m.group(1), m.group(2)
        svg = (ROOT / "assets" / "fig" / f"{name}.svg").read_text()
        return f'\n<figure id="fig-{name}">{svg}<figcaption>{escape(caption)}</figcaption></figure>\n'
    return re.sub(r"^\{\{fig:([\w-]+)\|(.+?)\}\}$", repl, body, flags=re.M)


def page(title, body, description="", canonical=""):
    tpl = (ROOT / "templates" / "base.html").read_text()
    return (tpl.replace("{{title}}", escape(title)).replace("{{site_title}}", escape(SITE["title"]))
               .replace("{{description}}", escape(description)).replace("{{canonical}}", canonical)
               .replace("{{year}}", str(date.today().year))
               .replace("{{body}}", body))


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "assets" / "models", OUT / "assets" / "models")
    shutil.copytree(ROOT / "assets" / "fig", OUT / "assets" / "fig")
    css = (ROOT / "templates" / "style.css").read_text()
    css += HtmlFormatter(style="friendly").get_style_defs(".highlight")
    css += "\n@media (prefers-color-scheme: dark) {\n" + "\n".join(
        "  " + line for line in HtmlFormatter(style="monokai").get_style_defs(".highlight").splitlines()) + "\n}\n"
    (OUT / "assets" / "style.css").write_text(css)
    (OUT / ".nojekyll").write_text("")

    posts = []
    for src in sorted((ROOT / "content" / "posts").glob("*.md"), reverse=True):
        meta, body = front_matter(src.read_text())
        slug = src.stem[11:]
        md = markdown.Markdown(extensions=["fenced_code", "codehilite", "tables", "toc", "attr_list", "sane_lists"],
                               extension_configs={"codehilite": {"guess_lang": False, "css_class": "highlight"},
                                                  "toc": {"permalink": "#", "permalink_title": "Link to this section"}})
        html = md.convert(figures(body))
        d = date.fromisoformat(meta["date"])
        article = (f'<article class="post"><header><p class="meta"><time datetime="{d}">{d:%B %-d, %Y}</time></p>'
                   f'<h1>{escape(meta["title"])}</h1></header>'
                   f'<nav class="toc" aria-label="Contents"><details><summary>Contents</summary>{md.toc}</details></nav>'
                   f'{html}</article>')
        url = f"/posts/{slug}/"
        (OUT / "posts" / slug).mkdir(parents=True)
        (OUT / "posts" / slug / "index.html").write_text(
            page(meta["title"], article, meta.get("description", ""), SITE["url"] + url))
        posts.append((d, meta, url))

    items = "".join(
        f'<li><time datetime="{d}">{d:%b %-d, %Y}</time><a href="{url}">{escape(m["title"])}</a>'
        f'<p>{escape(m.get("description", ""))}</p></li>' for d, m, url in posts)
    blog = f'<section class="intro"><h1>Blog</h1></section><ul class="posts">{items}</ul>'
    (OUT / "blog").mkdir()
    (OUT / "blog" / "index.html").write_text(page(f'Blog · {SITE["title"]}', blog, "Posts by Wenlong Wang.", SITE["url"] + "/blog/"))
    home = (f'<section class="home"><h1>{escape(SITE["title"])}</h1>'
            f'<p>{escape(SITE["tagline"])}</p>'
            f'<p class="links"><a href="/blog/">Blog →</a></p></section>')
    home_html = re.sub(r'<header class="site">.*?</header>\n|<footer class="site">.*?</footer>\n', "",
                       page(SITE["title"], home, SITE["tagline"], SITE["url"] + "/"))
    (OUT / "index.html").write_text(home_html)
    (OUT / "404.html").write_text(page("Not found", '<h1>Not found</h1><p><a href="/">Back to the home page</a></p>'))
    print("built", len(posts), "post(s) into", OUT)


if __name__ == "__main__":
    build()
