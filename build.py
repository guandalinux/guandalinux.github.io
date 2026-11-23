#!/usr/bin/env python3
"""Générateur du portfolio statique (bibliothèque standard uniquement).

Lit content/fr.json, content/en.json et content/diagrams.json, insère les
schémas SVG en ligne, et écrit le site dans docs/ (vidé à chaque lancement).
Termine par des contrôles : liens internes, parité des langues, lecture HTML.

Lancement : python3 build.py
"""

import base64
import html
import json
import posixpath
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
ASSETS_DIR = ROOT / "assets"
OUT_DIR = ROOT / "docs"

LANGS = ("fr", "en")
DEFAULT_LANG = "fr"
HOME = {"fr": "index.html", "en": "en/index.html"}
CASE = {"fr": "realisations/{slug}/index.html", "en": "en/work/{slug}/index.html"}
OG_LOCALE = {"fr": "fr_FR", "en": "en_GB"}
# Chemin de la racine du site une fois publié (« / » ou « /depot/ »), tiré de site.url par build() ; vide
# tant que l'adresse n'est pas renseignée. Seule la page 404 s'en sert : voir rel().
SITE_BASE = ""
SECTION_IDS = ("cases", "offer", "skills", "approach", "about", "contact")
# Variantes de rubrique sur l'accueil : "panel" (panneau blanc), "cta" (panneau en dégradé, texte centré),
# "split" (titre à gauche, texte à droite sur écran large).
SECTION_STYLE = {"offer": "panel", "about": "split", "contact": "cta"}
ROLE_KINDS = ("solo", "initiator", "contributor")
COPIED_ASSETS = ("css/site.css", "js/site.js", "favicon.svg",
                 "fonts/inter-latin-opsz-normal.woff2", "fonts/Inter-OFL.txt")
# Partie de la feuille de style qui référence un fichier (la police Inter), entre deux repères : la page
# 404, servie à toute profondeur avec ses styles en ligne, ne peut pas la garder.
FONT_BLOCK = re.compile(r"/\* police:debut \*/.*?/\* police:fin \*/\n*", re.S)
# Chaîne CSS entre guillemets, échappements compris ; commentaire hors chaîne (un « /* » dans une chaîne
# n'en ouvre pas un) ; url() à valeur entre guillemets ou nue.
CSS_STRING = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*\''''
CSS_COMMENT = re.compile(r"(" + CSS_STRING + r")|/\*.*?\*/", re.S)
CSS_URL = re.compile(r'''url\(\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|([^)\s"']*))\s*\)''', re.I | re.S)
CSS_UNREAD = re.compile(r"""@import\b|image-set\(\s*["']""", re.I)


def css_without_comments(css):
    return CSS_COMMENT.sub(lambda found: found.group(1) or "", css)


def css_file_refs(css):
    """Ce qu'une feuille de style va chercher hors d'elle-même.

    Rend la valeur de chaque url(), sauf les données en ligne (data:) et les renvois internes (#id),
    puis ce que cette lecture ne sait pas suivre et qu'il faut donc refuser : @import, image-set() à
    chaîne nue, url() qu'elle n'arrive pas à lire. Les commentaires sont ignorés et la casse ne compte
    pas, comme pour un navigateur."""
    css = css_without_comments(css)
    refs = []
    found = CSS_URL.findall(css)
    for double, single, bare in found:
        ref = (double or single or bare).strip()
        if ref and not ref.lower().startswith("data:") and not ref.startswith("#"):
            refs.append(ref)
    unread = sorted({item.lower() for item in CSS_UNREAD.findall(css)})
    if len(re.findall(r"url\(", css, re.I)) != len(found):
        unread.append("url( illisible")
    return refs, unread
LABEL_KEYS = ("period", "role", "context", "actions", "stack", "result", "handover", "note",
              "readCase", "allCases", "previousCase", "nextCase", "otherLanguage",
              "themeToggle", "motionToggle", "skipToContent", "diagram", "draftNotice")

# Seuls textes d'interface absents du contenu : la page 404, bilingue.
NOT_FOUND = {
    "fr": {"title": "Page introuvable", "text": "Cette page n'existe pas ou a été déplacée.",
           "home": "Retour à l'accueil"},
    "en": {"title": "Page not found", "text": "This page does not exist or has moved.",
           "home": "Back to the home page"},
}

# Posé avant le premier rendu : thème choisi et réglage « animations réduites » (pas de flash), puis
# la classe « entered », qui coupe l'entrée de page quand cette page a déjà été vue dans l'onglet ou
# qu'on arrive sur une ancre (« / » et « /index.html » comptent pour la même page). Un rechargement la rejoue.
THEME_BOOT = ('(function(){var r=document.documentElement;'
              'try{var t=localStorage.getItem("theme");'
              'if(t==="light"||t==="dark")r.setAttribute("data-theme",t);'
              'if(localStorage.getItem("motion")==="off")r.setAttribute("data-motion","off")}catch(e){}'
              'try{var k="seen:"+location.pathname.replace(/index\\.html$/,""),n=performance.getEntriesByType("navigation")[0];'
              'if(location.hash||(sessionStorage.getItem(k)&&!(n&&n.type==="reload")))r.classList.add("entered");'
              'sessionStorage.setItem(k,"1")}catch(e){}})();')

# Apparition mot à mot : écart entre deux mots, resserré pour les titres longs.
WORD_STEP_MS = 45
WORD_SPREAD_MS = 540

ICON_THEME = (
    '<svg class="icon icon-moon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">'
    '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linejoin="round"/></svg>'
    '<svg class="icon icon-sun" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">'
    '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/>'
    '<path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8'
    'M16.9 7.1l1.8-1.8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'
)

BADGE_MARK = {
    "solo": '<circle cx="6" cy="6" r="4.5" fill="currentColor"/>',
    "initiator": ('<circle cx="6" cy="6" r="4.25" fill="none" stroke="currentColor" stroke-width="1.5"/>'
                  '<path d="M6 1.75a4.25 4.25 0 0 0 0 8.5z" fill="currentColor"/>'),
    "contributor": '<circle cx="6" cy="6" r="4.25" fill="none" stroke="currentColor" stroke-width="1.5"/>',
}


class BuildError(Exception):
    """Erreur de contenu ou de construction, affichée sans trace Python."""


# ---------------------------------------------------------------- validation

S, S0 = "str", "str?"  # S0 : chaîne ou null (rubrique facultative)
SCHEMA = {
    "lang": S,
    "site": {"title": S, "description": S, "author": S, "url": S},
    "nav": [{"id": S, "label": S}],
    "hero": {k: S for k in ("kicker", "title", "lead", "availability", "primaryCta", "secondaryCta")},
    "figures": [{"value": S, "label": S, "detail": S}],
    "offer": {"title": S, "intro": S, "items": [{"title": S, "text": S, "caseIds": [S]}]},
    "cases": {
        "title": S, "intro": S,
        "roleLegend": {k: S for k in ROLE_KINDS},
        "items": [{"id": S, "slug": S, "title": S, "summary": S, "period": S, "roleKind": S,
                   "role": S, "context": S, "actions": [S], "stack": [S], "result": S0,
                   "handover": S0, "diagramId": S0, "note": S0}],
    },
    "skills": {"title": S, "intro": S, "groups": [{"name": S, "items": [{"name": S, "proof": S}]}]},
    "approach": {"title": S, "intro": S, "sections": [{"title": S, "text": S}]},
    "about": {"title": S, "paragraphs": [S]},
    "contact": {"title": S, "text": S, "links": [{"label": S, "href": S}], "pending": [S]},
    "footer": {"note": S},
    "labels": {k: S for k in LABEL_KEYS},
}
DIAGRAM_SCHEMA = [{"id": S, "files": {l: S for l in LANGS}, "title": {l: S for l in LANGS},
                   "caption": {l: S for l in LANGS}}]


def check(value, spec, where):
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            raise BuildError(f"{where} : objet attendu")
        for key, sub in spec.items():
            if key not in value:
                raise BuildError(f"clé manquante : {where}.{key}")
            check(value[key], sub, f"{where}.{key}")
    elif isinstance(spec, list):
        if not isinstance(value, list):
            raise BuildError(f"{where} : liste attendue")
        for i, item in enumerate(value):
            check(item, spec[0], f"{where}[{i}]")
    elif spec == S0:
        if value is not None and not isinstance(value, str):
            raise BuildError(f"{where} : chaîne ou null attendu")
    elif not isinstance(value, str):
        raise BuildError(f"{where} : chaîne attendue")


def load_json(path):
    if not path.is_file():
        raise BuildError(f"fichier introuvable : {path.relative_to(ROOT)}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{path.relative_to(ROOT)} : JSON invalide (ligne {exc.lineno}, colonne {exc.colno})")


def filled(value):
    return isinstance(value, str) and value.strip() != ""


def load_content():
    data = {}
    for lang in LANGS:
        d = load_json(CONTENT_DIR / f"{lang}.json")
        check(d, SCHEMA, f"{lang}.json")
        if d["lang"] != lang:
            raise BuildError(f"{lang}.json : lang vaut « {d['lang']} », attendu « {lang} »")
        data[lang] = d

    raw = load_json(CONTENT_DIR / "diagrams.json")
    check(raw, DIAGRAM_SCHEMA, "diagrams.json")
    diagrams, svgs = {}, {}
    for entry in raw:
        diagrams[entry["id"]] = entry

    ids = {lang: [c["id"] for c in data[lang]["cases"]["items"]] for lang in LANGS}
    if ids["fr"] != ids["en"]:
        raise BuildError("les études de cas doivent avoir les mêmes id, dans le même ordre, en fr et en en")

    for lang in LANGS:
        d, f = data[lang], f"{lang}.json"
        unknown = {n["id"] for n in d["nav"]} - set(SECTION_IDS)
        if unknown:
            raise BuildError(f"{f} : nav contient des id inconnus {sorted(unknown)} (attendus : {SECTION_IDS})")
        slugs = [c["slug"] for c in d["cases"]["items"]]
        if len(set(slugs)) != len(slugs):
            raise BuildError(f"{f} : slugs d'études de cas en double")
        for i, c in enumerate(d["cases"]["items"]):
            where = f"{f} cases.items[{i}]"
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", c["slug"]):
                raise BuildError(f"{where}.slug invalide : « {c['slug']} » (minuscules, chiffres, tirets)")
            if c["roleKind"] not in ROLE_KINDS:
                raise BuildError(f"{where}.roleKind inconnu : « {c['roleKind']} » (attendus : {ROLE_KINDS})")
            if filled(c["diagramId"]):
                did = c["diagramId"]
                if did not in diagrams:
                    raise BuildError(f"{where}.diagramId « {did} » absent de diagrams.json")
                key = (did, lang)
                if key not in svgs:
                    svgs[key] = load_svg(diagrams[did]["files"][lang])
        for i, item in enumerate(d["offer"]["items"]):
            for cid in item["caseIds"]:
                if cid not in ids[lang]:
                    raise BuildError(f"{f} offer.items[{i}].caseIds : étude « {cid} » inconnue")
        for i, link in enumerate(d["contact"]["links"]):
            if not link["href"].startswith(("https://", "mailto:")):
                raise BuildError(f"{f} contact.links[{i}].href doit commencer par https:// ou mailto:")
    return data, diagrams, svgs


def site_address(data):
    """Nom de domaine et chemin de la racine du site publié, d'après site.url : « / » pour
    https://exemple.github.io/, « /depot/ » pour https://exemple.github.io/depot/. Deux chaînes vides
    tant que l'adresse n'est pas renseignée."""
    urls = {data[lang]["site"]["url"].strip() for lang in LANGS}
    if len(urls) != 1:
        raise BuildError("site.url doit être identique dans fr.json et en.json")
    url = urls.pop()
    if not url:
        return "", ""
    # Dossiers en lettres, chiffres et . _ ~ - ; ni « . » ni « .. », que le navigateur ferait disparaître.
    found = re.fullmatch(r"https://([A-Za-z0-9.-]+)(/(?:(?!\.{1,2}/)[A-Za-z0-9._~-]+/)*)", url)
    if not found:
        raise BuildError(f"site.url invalide : « {url} ». Attendu l'adresse que verront les visiteurs, en https et "
                         "avec sa barre finale, par exemple https://exemple.github.io/ ou "
                         "https://exemple.github.io/depot/ (un nom de domaine accentué s'écrit sous sa forme « xn-- »)")
    return found.group(1), found.group(2)


def from_site_root(link):
    """Lien de la page 404, écrit depuis la racine du site, ramené au lien équivalent d'une page posée à
    cette racine (la racine seule vaut sa page d'accueil) ; None s'il ne part pas de la racine du site."""
    if not link.startswith(SITE_BASE) or link.startswith("//"):
        return None
    target, sep, frag = link[len(SITE_BASE):].partition("#")
    return (target or "index.html") + sep + frag


def load_svg(rel_path):
    path = (ROOT / rel_path).resolve()
    if ASSETS_DIR.resolve() not in path.parents or not path.is_file():
        raise BuildError(f"schéma introuvable ou hors de assets/ : {rel_path}")
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<\?xml.*?\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", text, flags=re.S | re.I)
    start = text.find("<svg")
    if start < 0 or "</svg>" not in text:
        raise BuildError(f"{rel_path} : balise <svg> introuvable")
    if re.search(r"<script|\son\w+\s*=|(?:xlink:)?href\s*=\s*[\"'](?!#)", text, re.I):
        raise BuildError(f"{rel_path} : script, gestionnaire d'événement ou lien externe interdit dans un schéma")
    return text[start:].strip()


# ---------------------------------------------------------------- helpers

def typo(text, lang):
    """Espaces insécables : mise en page uniquement, le texte reste identique."""
    if lang == "fr":
        previous = None
        while previous != text:
            previous = text
            text = re.sub(r"(\d) (\d{3})(?!\d)", "\\1\u202f\\2", text)
        text = re.sub(r" ([:;!?%»])", "\u00a0\\1", text)
        text = text.replace("« ", "«\u00a0")
    return re.sub(r"(\d) (min|Go|Mo|GB|MB|h)\b", "\\1\u00a0\\2", text)


def rel(src, dst):
    """Lien de la page src vers dst (chemins depuis la racine du site).

    Relatif partout, sauf depuis la page 404 : l'hébergeur la sert telle quelle à l'adresse fautive, à
    n'importe quelle profondeur, où un lien relatif mènerait ailleurs. Ses liens partent donc de la
    racine du site dès que son adresse est connue (SITE_BASE)."""
    target, sep, frag = dst.partition("#")
    if target == src:
        return f"#{frag}" if sep else posixpath.basename(src)
    if src == "404.html" and SITE_BASE:
        return SITE_BASE + dst
    out = posixpath.relpath(target, posixpath.dirname(src) or ".")
    return out + (f"#{frag}" if sep else "")


def q(value):
    return html.escape(value, quote=True)


# ---------------------------------------------------------------- rendu

class Renderer:
    def __init__(self, lang, data, diagrams, svgs):
        self.lang = lang
        self.other = "en" if lang == "fr" else "fr"
        self.d = data[lang]
        self.od = data[self.other]
        self.L = self.d["labels"]
        self.cases = self.d["cases"]["items"]
        self.legend = self.d["cases"]["roleLegend"]
        self.diagrams = diagrams
        self.svgs = svgs
        self.colon = "\u00a0: " if lang == "fr" else ": "

    def t(self, s):
        return html.escape(typo(s, self.lang), quote=False)

    def a(self, s):
        return html.escape(typo(s, self.lang), quote=True)

    def words(self, s):
        """Titre découpé en mots pour l'apparition mot à mot (chaque mot porte son rang).
        À poser dans un titre qui porte aussi aria-label : les lecteurs d'écran lisent le
        titre d'un seul tenant, les mots découpés leur sont masqués."""
        parts = typo(s, self.lang).split(" ")
        step = ""
        if len(parts) * WORD_STEP_MS > WORD_SPREAD_MS:
            step = f' style="--step:{max(16, WORD_SPREAD_MS // len(parts))}ms"'
        spans = " ".join(f'<span class="w" style="--i:{i}">{html.escape(part, quote=False)}</span>'
                         for i, part in enumerate(parts))
        return f'<span class="words" aria-hidden="true"{step}>{spans}</span>'

    def btn(self, kind, href, label, attrs=""):
        """Bouton en pilule ; le libellé est isolé pour pouvoir glisser quand la flèche apparaît."""
        return (f'<a class="btn btn-{kind}" href="{q(href)}"{attrs}>'
                f'<span class="btn-label">{label}</span></a>')

    def case_path(self, idx, lang=None):
        lang = lang or self.lang
        d = self.d if lang == self.lang else self.od
        return CASE[lang].format(slug=d["cases"]["items"][idx]["slug"])

    def badge(self, kind):
        return (f'<span class="badge badge--{kind}"><svg class="badge-mark" viewBox="0 0 12 12" '
                f'aria-hidden="true" focusable="false">{BADGE_MARK[kind]}</svg>{self.t(self.legend[kind])}</span>')

    # --- gabarit commun

    def header(self, path, alt_path, with_nav=True):
        L, o = self.L, self.other
        nav = ""
        if with_nav:
            items = "".join(
                f'<li><a href="{q(rel(path, HOME[self.lang] + "#" + n["id"]))}">{self.t(n["label"])}</a></li>'
                for n in self.d["nav"])
            nav = f'\n    <nav class="site-nav"><ul>{items}</ul></nav>'
        return f"""<a class="skip-link" href="#main">{self.t(L["skipToContent"])}</a>
<header class="site-header">
  <div class="header-bar">
    <a class="brand" href="{q(rel(path, HOME[self.lang]))}">{self.t(self.d["site"]["author"])}</a>{nav}
    <div class="header-tools">
      <a class="lang-switch" href="{q(rel(path, alt_path))}" hreflang="{o}" lang="{o}"><span class="lang-full">{html.escape(L["otherLanguage"])}</span> <span class="lang-code">{o.upper()}</span></a>
      <button class="theme-toggle" type="button" data-theme-toggle aria-label="{self.a(L["themeToggle"])}" title="{self.a(L["themeToggle"])}" hidden>{ICON_THEME}</button>
    </div>
  </div>
</header>"""

    def footer(self, path, alt_path):
        o = self.other
        return f"""<footer class="site-footer">
  <div class="wrap footer-inner">
    <p class="footer-author">{self.t(self.d["site"]["author"])}</p>
    <p class="footer-note">{self.t(self.d["footer"]["note"])}</p>
    <div class="footer-tools">
      <a class="footer-lang" href="{q(rel(path, alt_path))}" hreflang="{o}" lang="{o}">{html.escape(self.L["otherLanguage"])}</a>
      <button class="motion-toggle" type="button" data-motion-toggle aria-pressed="false" hidden>{self.t(self.L["motionToggle"])}</button>
    </div>
  </div>
</footer>"""

    def document(self, path, title, description, alt_path, main, og_type="website",
                 with_nav=True, inline=None):
        lang, other = self.lang, self.other
        alternates = {lang: path, other: alt_path}
        hreflang = "\n".join(
            f'<link rel="alternate" hreflang="{l}" href="{q(rel(path, alternates[l]))}">' for l in LANGS)
        hreflang += f'\n<link rel="alternate" hreflang="x-default" href="{q(rel(path, alternates[DEFAULT_LANG]))}">'
        if inline:
            hreflang = ""   # page d'erreur : pas de versions de langue à annoncer
            icon = inline["icon"]
            assets_head = f"<style>\n{inline['css']}</style>"
            assets_body = f"<script>\n{inline['js']}</script>\n"
        else:
            icon = rel(path, "assets/favicon.svg")
            assets_head = (f'<link rel="stylesheet" href="{q(rel(path, "assets/css/site.css"))}">\n'
                           f'<script src="{q(rel(path, "assets/js/site.js"))}" defer></script>')
            assets_body = ""
        author = self.d["site"]["author"]
        return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{self.t(title)}</title>
<meta name="description" content="{self.a(description)}">
<meta name="author" content="{self.a(author)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f7f5ef" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#121211" media="(prefers-color-scheme: dark)">
{hreflang}
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{self.a(title)}">
<meta property="og:description" content="{self.a(description)}">
<meta property="og:site_name" content="{self.a(author)}">
<meta property="og:locale" content="{OG_LOCALE[lang]}">
<meta property="og:locale:alternate" content="{OG_LOCALE[other]}">
<link rel="icon" href="{q(icon)}" type="image/svg+xml">
<script>{THEME_BOOT}</script>
{assets_head}
</head>
<body>
{self.header(path, alt_path, with_nav)}
{main}
{self.footer(path, alt_path)}
{assets_body}</body>
</html>
"""

    # --- accueil

    def section(self, sid, title, intro, body):
        num = f"{SECTION_IDS.index(sid) + 1:02d}"
        intro_html = f'\n      <p class="section-intro">{self.t(intro)}</p>' if filled(intro) else ""
        kind = SECTION_STYLE.get(sid)
        variant = f" section--{kind}" if kind else ""
        box = {"panel": "panel", "cta": "panel art"}.get(kind, "wrap")
        return f"""<section id="{sid}" class="section{variant}" aria-labelledby="{sid}-title">
  <div class="{box}">
    <header class="section-head" data-reveal="head">
      <p class="section-index" aria-hidden="true">{num}</p>
      <h2 id="{sid}-title" aria-label="{self.a(title)}">{self.words(title)}</h2>{intro_html}
    </header>
{body}
  </div>
</section>"""

    def render_home(self):
        d, L = self.d, self.L
        path, alt = HOME[self.lang], HOME[self.other]
        hero = d["hero"]
        index_of = {c["id"]: i for i, c in enumerate(self.cases)}

        figures = "\n".join(
            f'      <li class="figure" data-reveal><p class="figure-value"><span class="vh">{self.t(f["value"])}</span>'
            f'<span class="figure-num" aria-hidden="true" data-count>{self.t(f["value"])}</span></p>'
            f'<p class="figure-label">{self.t(f["label"])}</p>'
            f'<p class="figure-detail">{self.t(f["detail"])}</p></li>'
            for f in d["figures"])

        legend = "".join(f"<li>{self.badge(k)}</li>" for k in ROLE_KINDS)
        cards = []
        for i, c in enumerate(self.cases):
            cards.append(f"""      <li class="case-card" data-reveal="tile">
        <div class="case-card-top"><span class="case-num">{i + 1:02d}</span>{self.badge(c["roleKind"])}</div>
        <h3 class="case-card-title"><a class="card-link" href="{q(rel(path, self.case_path(i)))}">{self.t(c["title"])}</a></h3>
        <p class="case-card-summary">{self.t(c["summary"])}</p>
        <div class="case-card-foot">
          <p class="case-card-period"><span class="vh">{self.t(L["period"] + self.colon)}</span>{self.t(c["period"])}</p>
          <span class="case-card-more" aria-hidden="true">{self.t(L["readCase"])} <span class="arrow">→</span></span>
        </div>
      </li>""")
        cases_body = (f'    <ul class="role-legend" data-reveal>{legend}</ul>\n'
                      f'    <ol class="case-list">\n' + "\n".join(cards) + "\n    </ol>")

        offers = []
        for item in d["offer"]["items"]:
            chips = " ".join(
                f'<a class="case-chip" href="{q(rel(path, self.case_path(index_of[cid])))}" '
                f'title="{self.a(self.cases[index_of[cid]]["title"])}" '
                f'aria-label="{index_of[cid] + 1:02d} — {self.a(self.cases[index_of[cid]]["title"])}">'
                f'{index_of[cid] + 1:02d}</a>'
                for cid in item["caseIds"])
            chips_html = (f'<p class="offer-cases"><span class="offer-cases-label">{self.t(d["cases"]["title"])}</span> '
                          f'{chips}</p>') if chips else ""
            offers.append(f'      <li class="offer-item" data-reveal><h3>{self.t(item["title"])}</h3>'
                          f'<p class="offer-text">{self.t(item["text"])}</p>{chips_html}</li>')
        offer_body = '    <ol class="offer-list">\n' + "\n".join(offers) + "\n    </ol>"

        groups = []
        for g in d["skills"]["groups"]:
            rows = "".join(f'<li><span class="skill-name">{self.t(s["name"])}</span>'
                           f'<span class="skill-proof">{self.t(s["proof"])}</span></li>' for s in g["items"])
            groups.append(f'      <div class="skill-group"><h3>{self.t(g["name"])}</h3>'
                          f'<ul class="skill-list">{rows}</ul></div>')
        skills_body = '    <div class="skill-groups" data-reveal="cols">\n' + "\n".join(groups) + "\n    </div>"

        approach_body = '    <div class="approach-grid">\n' + "\n".join(
            f'      <div class="approach-item" data-reveal><h3>{self.t(s["title"])}</h3><p>{self.t(s["text"])}</p></div>'
            for s in d["approach"]["sections"]) + "\n    </div>"

        about_body = '    <div class="about-text">\n' + "\n".join(
            f'      <p data-reveal{"=" + chr(34) + "focus" + chr(34) if i == 0 else ""}>{self.t(p)}</p>'
            for i, p in enumerate(d["about"]["paragraphs"])) + "\n    </div>"

        contact = d["contact"]
        links = "".join("<li>" + self.btn("secondary", l["href"], self.t(l["label"]), ' rel="me noopener"') + "</li>"
                        for l in contact["links"])
        contact_body = f'    <p class="contact-text" data-reveal>{self.t(contact["text"])}</p>'
        if links:
            contact_body += f'\n    <ul class="contact-links" data-reveal>{links}</ul>'
        pending = [p for p in contact["pending"] if filled(p)]
        if pending:
            items = "".join(f"<li>{self.t(p)}</li>" for p in pending)
            contact_body += (f'\n    <aside class="draft-notice" data-reveal><p class="draft-title">{self.t(L["draftNotice"])}</p>'
                             f"<ul>{items}</ul></aside>")

        sections = {
            "cases": (d["cases"]["title"], d["cases"]["intro"], cases_body),
            "offer": (d["offer"]["title"], d["offer"]["intro"], offer_body),
            "skills": (d["skills"]["title"], d["skills"]["intro"], skills_body),
            "approach": (d["approach"]["title"], d["approach"]["intro"], approach_body),
            "about": (d["about"]["title"], "", about_body),
            "contact": (contact["title"], "", contact_body),
        }
        main = f"""<main id="main">
<section class="hero" aria-labelledby="hero-title">
  <div class="panel art">
    <p class="kicker">{self.t(hero["kicker"])}</p>
    <h1 id="hero-title" aria-label="{self.a(hero["title"])}">{self.words(hero["title"])}</h1>
    <p class="hero-lead">{self.t(hero["lead"])}</p>
    <p class="hero-actions">{self.btn("primary", "#cases", self.t(hero["primaryCta"]))} {self.btn("secondary", "#contact", self.t(hero["secondaryCta"]))}</p>
    <p class="availability"><span class="status-dot" aria-hidden="true"></span>{self.t(hero["availability"])}</p>
  </div>
</section>
<div class="figures-band">
  <div class="wrap">
    <ul class="figures">
{figures}
    </ul>
  </div>
</div>
""" + "\n".join(self.section(sid, *sections[sid]) for sid in SECTION_IDS) + "\n</main>"
        return path, self.document(path, d["site"]["title"], d["site"]["description"], alt, main)

    # --- étude de cas

    def render_case(self, idx):
        L, c = self.L, self.cases[idx]
        path, alt = self.case_path(idx), self.case_path(idx, self.other)
        total = len(self.cases)

        def block(key, inner, extra=""):
            return (f'  <section class="case-section{extra}" aria-labelledby="{key}-title" data-reveal>\n'
                    f'    <h2 id="{key}-title">{self.t(L[key])}</h2>\n{inner}\n  </section>')

        parts = [block("context", f'    <p>{self.t(c["context"])}</p>')]
        if c["actions"]:
            items = "\n".join(f"      <li>{self.t(x)}</li>" for x in c["actions"])
            parts.append(block("actions", f'    <ol class="action-list">\n{items}\n    </ol>'))
        if c["stack"]:
            tags = "".join(f"<li>{self.t(x)}</li>" for x in c["stack"])
            parts.append(block("stack", f'    <ul class="tags">{tags}</ul>'))
        if filled(c["diagramId"]):
            dg = self.diagrams[c["diagramId"]]
            title, caption = dg["title"][self.lang], dg["caption"][self.lang]
            parts.append(block("diagram", f"""    <figure class="diagram">
      <div class="diagram-scroll" tabindex="0" role="region" aria-label="{self.a(title)}">
{self.svgs[(c["diagramId"], self.lang)]}
      </div>
      <figcaption><span class="diagram-title">{self.t(title)}</span>{self.t(caption)}</figcaption>
    </figure>""", " case-diagram"))
        if filled(c["result"]):
            parts.append(block("result", f'    <p>{self.t(c["result"])}</p>', " case-result"))
        if filled(c["handover"]):
            parts.append(block("handover", f'    <p>{self.t(c["handover"])}</p>'))
        if filled(c["note"]):
            parts.append(block("note", f'    <p>{self.t(c["note"])}</p>', " case-note"))

        pager = []
        if idx > 0:
            pager.append(f'<a class="pager-link pager-prev" rel="prev" href="{q(rel(path, self.case_path(idx - 1)))}" data-reveal="tile">'
                         f'<span class="pager-dir"><span class="arrow" aria-hidden="true">←</span> {self.t(L["previousCase"])}</span>'
                         f'<span class="pager-title">{self.t(self.cases[idx - 1]["title"])}</span></a>')
        if idx < total - 1:
            pager.append(f'<a class="pager-link pager-next" rel="next" href="{q(rel(path, self.case_path(idx + 1)))}" data-reveal="tile">'
                         f'<span class="pager-dir">{self.t(L["nextCase"])} <span class="arrow" aria-hidden="true">→</span></span>'
                         f'<span class="pager-title">{self.t(self.cases[idx + 1]["title"])}</span></a>')

        main = f"""<main id="main">
<article class="case">
  <div class="wrap">
  <p class="crumb"><a href="{q(rel(path, HOME[self.lang] + "#cases"))}"><span class="arrow" aria-hidden="true">←</span>{self.t(L["allCases"])}</a></p>
  <header class="case-head">
    <p class="case-index">{idx + 1:02d} / {total:02d}</p>
    <h1 aria-label="{self.a(c["title"])}">{self.words(c["title"])}</h1>
    <p class="case-lead">{self.t(c["summary"])}</p>
    <dl class="facts">
      <div class="fact fact-period"><dt>{self.t(L["period"])}</dt><dd>{self.t(c["period"])}</dd></div>
      <div class="fact fact-role"><dt>{self.t(L["role"])}</dt><dd>{self.badge(c["roleKind"])}<p>{self.t(c["role"])}</p></dd></div>
    </dl>
  </header>
  <div class="case-body">
{chr(10).join(parts)}
  </div>
  <nav class="pager" aria-label="{self.a(self.d["cases"]["title"])}">
    {chr(10).join(pager)}
  </nav>
  </div>
</article>
</main>"""
        title = f'{c["title"]} — {self.d["site"]["author"]}'
        return path, self.document(path, title, c["summary"], alt, main, og_type="article")

    # --- 404 (autonome : styles en ligne, car servie à toute profondeur)

    def render_404(self):
        path = "404.html"
        fr, en = NOT_FOUND["fr"], NOT_FOUND["en"]
        css, removed = FONT_BLOCK.subn("", (ASSETS_DIR / "css/site.css").read_text(encoding="utf-8"))
        refs, unread = css_file_refs(css)
        faces = len(re.findall(r"@font-face\s*\{", css_without_comments(css), re.I))
        if removed != 1 or refs or unread or faces:
            raise BuildError("page 404 : sa feuille de style est mise dans la page et ne peut référencer aucun fichier. "
                             f"Blocs entre repères police:debut et police:fin retirés : {removed} (attendu : 1) ; "
                             f"@font-face restants : {faces} ; références restantes : {', '.join(refs + unread) or 'aucune'}")
        js = (ASSETS_DIR / "js/site.js").read_text(encoding="utf-8")
        icon = "data:image/svg+xml;base64," + base64.b64encode((ASSETS_DIR / "favicon.svg").read_bytes()).decode()
        main = f"""<main id="main">
<section class="notfound">
  <div class="wrap">
    <h1>{self.t(fr["title"])}</h1>
    <p>{self.t(fr["text"])}</p>
    <p class="notfound-action">{self.btn("primary", rel(path, HOME["fr"]), self.t(fr["home"]))}</p>
    <div class="notfound-alt" lang="en">
      <h2>{html.escape(en["title"])}</h2>
      <p>{html.escape(en["text"])}</p>
      <p class="notfound-action">{self.btn("secondary", rel(path, HOME["en"]), html.escape(en["home"]))}</p>
    </div>
  </div>
</section>
</main>"""
        title = f'{fr["title"]} — {self.d["site"]["author"]}'
        return path, self.document(path, title, fr["text"], HOME["en"], main, with_nav=False,
                                   inline={"css": css, "js": js, "icon": icon})


# ---------------------------------------------------------------- contrôles

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.ids, self.errors, self.stack = [], set(), [], []
        self.h1 = 0
        self.lang = None

    def _attrs(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            if a["id"] in self.ids:
                self.errors.append(f"id en double : {a['id']}")
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "h1":
            self.h1 += 1
        for key in ("href", "src"):
            if a.get(key):
                self.links.append((tag, a[key]))

    def handle_starttag(self, tag, attrs):
        self._attrs(tag, attrs)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._attrs(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
            return
        self.errors.append(f"balise fermante inattendue </{tag}> (ouvertes : {self.stack[-3:]})")
        if tag in self.stack:
            while self.stack.pop() != tag:
                pass


def run_checks(written):
    errors, pages = [], {}
    for rel_path in written:
        if not rel_path.endswith(".html"):
            continue
        parser = Inspector()
        try:
            parser.feed((OUT_DIR / rel_path).read_text(encoding="utf-8"))
            parser.close()
        except Exception as exc:  # noqa: BLE001 - toute erreur de lecture est signalée
            errors.append(f"{rel_path} : lecture HTML impossible ({exc})")
            continue
        if parser.stack:
            parser.errors.append(f"balises non fermées : {parser.stack}")
        if parser.h1 != 1:
            parser.errors.append(f"{parser.h1} titre(s) h1 au lieu de 1")
        if parser.lang not in LANGS:
            parser.errors.append("attribut lang absent ou inconnu")
        errors += [f"{rel_path} : {e}" for e in parser.errors]
        pages[rel_path] = parser

    checked = 0
    for rel_path, parser in pages.items():
        for tag, link in parser.links:
            if re.match(r"^[a-z][a-z0-9+.-]*:", link, re.I):
                if tag in ("link", "script", "img", "source") and not link.startswith("data:"):
                    errors.append(f"{rel_path} : ressource externe interdite {link}")
                continue
            if rel_path == "404.html" and SITE_BASE and not link.startswith("#"):
                # Servie à toute profondeur : ses liens partent de la racine du site (voir rel()), puis
                # sont contrôlés comme ceux d'une page posée à cette racine.
                rooted = from_site_root(link)
                if rooted is None:
                    errors.append(f"{rel_path} : lien {link} à faire partir de la racine du site ({SITE_BASE})")
                    continue
                link = rooted
            if link.startswith(("/", "//")):
                errors.append(f"{rel_path} : lien non relatif {link}")
                continue
            target, _, frag = link.partition("#")
            target = target.split("?")[0]
            if target:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel_path), target))
                if resolved.startswith(".."):
                    errors.append(f"{rel_path} : lien hors du site {link}")
                    continue
                file = OUT_DIR / resolved
                if file.is_dir():
                    file = file / "index.html"
                if not file.is_file():
                    errors.append(f"{rel_path} : lien cassé {link}")
                    continue
                target = file.relative_to(OUT_DIR).as_posix()
            else:
                target = rel_path
            if frag and target in pages and frag not in pages[target].ids:
                errors.append(f"{rel_path} : ancre absente {link}")
            checked += 1

    # La feuille de style ne référence que des fichiers du site présents dans la sortie (la police).
    css_path = "assets/css/site.css"
    refs, unread = css_file_refs((OUT_DIR / css_path).read_text(encoding="utf-8"))
    for found in unread:
        errors.append(f"{css_path} : « {found} » n'est pas suivi par ce contrôle, donc interdit")
    for ref in refs:
        if re.match(r"^[a-z][a-z0-9+.-]*:", ref, re.I) or ref.startswith("/"):
            errors.append(f"{css_path} : ressource externe ou non relative interdite {ref}")
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(css_path), re.split(r"[?#]", ref)[0]))
        if resolved.startswith("..") or not (OUT_DIR / resolved).is_file():
            errors.append(f"{css_path} : fichier référencé absent {ref}")

    counts = {"fr": 0, "en": 0}
    for rel_path in pages:
        if rel_path == "404.html":
            continue
        counts["en" if rel_path.startswith("en/") else "fr"] += 1
    if counts["fr"] != counts["en"]:
        errors.append(f"nombre de pages différent : fr {counts['fr']}, en {counts['en']}")
    return errors, checked, counts, len(pages)


# ---------------------------------------------------------------- build

def build():
    global SITE_BASE
    data, diagrams, svgs = load_content()
    host, SITE_BASE = site_address(data)
    # Domaine personnalisé : GitHub Pages dépose un fichier CNAME dans le dossier publié. Il est conservé
    # d'une construction à l'autre, et l'adresse du site doit lui correspondre : avec un tel domaine le
    # site est servi à sa racine, même depuis un dépôt de projet.
    cname_file = OUT_DIR / "CNAME"
    cname = (cname_file.read_text(encoding="utf-8").split() or [""])[0] if cname_file.is_file() else ""
    if cname and host and (cname.lower() != host.lower() or SITE_BASE != "/"):
        raise BuildError(f"site.url ne correspond pas au domaine personnalisé du site (docs/CNAME : {cname}) : "
                         f"avec ce domaine le site est servi à sa racine, site.url doit valoir https://{cname}/")

    if OUT_DIR.exists():
        if OUT_DIR.resolve().parent != ROOT or OUT_DIR.name != "docs":
            raise BuildError(f"dossier de sortie inattendu : {OUT_DIR}")
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir()

    written = []

    def write(rel_path, content, binary=False):
        target = OUT_DIR / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        written.append(rel_path)

    for asset in COPIED_ASSETS:
        src = ASSETS_DIR / asset
        if not src.is_file():
            raise BuildError(f"fichier source manquant : assets/{asset}")
        write(f"assets/{asset}", src.read_bytes(), binary=True)

    for lang in LANGS:
        r = Renderer(lang, data, diagrams, svgs)
        write(*r.render_home())
        for idx in range(len(r.cases)):
            write(*r.render_case(idx))
    write(*Renderer(DEFAULT_LANG, data, diagrams, svgs).render_404())
    if cname:
        write("CNAME", cname + "\n")
    write(".nojekyll", "")
    write("robots.txt", "User-agent: *\nAllow: /\n")

    errors, checked, counts, html_pages = run_checks(written)
    print(f"Pages écrites : {html_pages} (fr : {counts['fr']}, en : {counts['en']}, 404 : 1) dans {OUT_DIR.relative_to(ROOT)}/")

    for lang in LANGS:
        pending = [p for p in data[lang]["contact"]["pending"] if filled(p)]
        if pending:
            print(f"AVERTISSEMENT : contenu à compléter avant publication ({lang}.json, contact.pending) : "
                  + ", ".join(pending))
    if not SITE_BASE:
        print("AVERTISSEMENT : adresse du site à renseigner avant publication (site.url, dans fr.json et en.json) : "
              "sans elle, les liens de la page 404 ne fonctionnent que pour une adresse fautive à la racine du site"
              + (f" (d'après docs/CNAME, ce serait https://{cname}/)" if cname else ""))

    if errors:
        print(f"Contrôles : ÉCHEC, {len(errors)} erreur(s)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"Contrôles : OK ({checked} liens internes vérifiés, fr et en à parité, "
          f"{html_pages} fichiers HTML lus sans erreur)")
    return 0


def main():
    try:
        return build()
    except BuildError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
