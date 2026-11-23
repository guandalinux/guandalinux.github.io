# Portfolio — site statique

Site bilingue (français par défaut, anglais sous `en/`) généré dans `docs/` pour GitHub Pages.

## Modifier le contenu

- Textes : `content/fr.json` et `content/en.json`, de structure identique (mêmes clés, mêmes études de cas dans le même ordre).
- Une rubrique d'étude de cas vide (`""` ou `null` pour `result`, `handover`, `note`, `diagramId`) n'est pas affichée.
- Schémas : `content/diagrams.json` et `assets/diagrams/<id>.<langue>.svg`, insérés en ligne ; couleurs via `--diagram-*`.
- Mise en page : `assets/css/site.css`, rendu HTML : `build.py`.
- Police : celle d'Apple, San Francisco, nommée par `--font-display` et `--font-sans` en tête de `assets/css/site.css`.
  Elle s'affiche sur Mac, iPhone et iPad, qui la fournissent ; la licence d'Apple interdit de la servir depuis un site.
  Les autres appareils reçoivent Inter, une police libre très proche, servie par le site lui-même :
  `assets/fonts/inter-latin-opsz-normal.woff2` (72 920 octets, variable en graisse et en taille optique, alphabet latin)
  et sa licence `assets/fonts/Inter-OFL.txt`, à garder à côté du fichier. Provenance : paquet
  `@fontsource-variable/inter` 5.3.0, téléchargé le 23 novembre 2026 depuis cdn.jsdelivr.net, SHA-256
  `2c295d99e26dcf357d4d01bcf270fd6924b600c9a13dd8c363ef114f4c6976fa` (l'empreinte publiée pour ce paquet).
  La page 404, autonome, n'embarque pas la police : elle prend la police d'interface de l'appareil. Dans `site.css`,
  les repères `police:debut` et `police:fin` délimitent ce que la construction lui retire ; ne pas les enlever.
  Le temps qu'Inter arrive (première visite, connexion lente), une police de l'appareil réglée à sa largeur tient sa
  place : ce sont les blocs « Inter attente » de `site.css`, fondés sur Arial et ses équivalentes ; Android n'en a pas.
  Pour la même raison les largeurs de lecture sont en `em` et non en `ch` : le `ch` change d'une police à l'autre.
- Animations : rubrique « Mouvement » de `assets/css/site.css` et `assets/js/site.js` (thème, apparitions au défilement,
  chiffres qui comptent, lumière et inclinaison sous la souris, en-tête qui s'efface, bouton « Réduire les animations »).
  Un bloc s'anime à son entrée dans la fenêtre s'il porte l'attribut `data-reveal` dans `build.py` ; avec la valeur `tile`,
  il se redresse comme une tuile. L'entrée de page ne joue qu'une fois par onglet ; un rechargement la rejoue.
  Sans JavaScript, ou si le système demande moins de mouvement, tout est affiché d'emblée.

## Reconstruire

    python3 build.py

Le script vide `docs/`, écrit les pages, puis contrôle les liens internes, la parité fr/en et la lecture HTML.
Il s'arrête en erreur si une clé manque. Tant que `contact.pending` n'est pas vide, il affiche
« contenu à compléter avant publication » et le site montre un encadré de version de travail.

## Prévisualiser en local

    cd docs && python3 -m http.server 8000

Puis ouvrir http://localhost:8000/ (tous les liens sont relatifs : racine de domaine ou sous-dossier).
Ce serveur n'envoie pas d'en-tête de cache : si une page semble ancienne après une reconstruction, forcer le
rechargement (Ctrl+Maj+R).

## Publier

1. Renseigner dans `site.url` l'adresse que verront les visiteurs, la même dans `content/fr.json` et
   `content/en.json`, en https et avec sa barre finale :
   - site d'utilisateur (dépôt `compte.github.io`) : `https://compte.github.io/` ;
   - site de projet (tout autre dépôt) : `https://compte.github.io/depot/` ;
   - domaine personnalisé : `https://domaine/`, même depuis un dépôt de projet, car le site est alors servi à la
     racine du domaine. GitHub dépose dans ce cas un fichier `CNAME` dans `docs/` : le récupérer (`git pull`) avant
     de reconstruire. La construction le conserve et refuse une `site.url` qui ne lui correspond pas.

   La page 404 a besoin de cette adresse : GitHub Pages la sert à l'adresse fautive, à n'importe quelle profondeur, et
   ses liens doivent partir de la racine du site. Sans elle ils restent relatifs et ne fonctionnent que pour une faute
   à la racine. Si l'adresse change (domaine ajouté ou retiré, dépôt renommé), corriger `site.url` et reconstruire.
   En local, une fois une adresse en sous-dossier renseignée, les liens de `404.html` ne mènent plus nulle part : c'est
   attendu, le serveur local sert le site à la racine.
2. Vider `contact.pending` après avoir ajouté les liens définitifs, puis relancer `python3 build.py`.
3. Commiter `docs/` avec le reste du projet et pousser sur GitHub.
4. Dans le dépôt : Settings > Pages > Deploy from a branch, branche `main`, dossier `/docs`.
