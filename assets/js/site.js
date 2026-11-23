/* Thème, mouvement, apparitions au défilement et effets au pointeur. Aucune dépendance.
   Le thème et le réglage « animations réduites » sont posés avant le premier rendu par un
   script en ligne dans le head ; ici, les bascules et tout ce qui dépend du défilement ou de la souris.

   Principe de sûreté : rien n'est masqué tant que ce script n'a pas tourné, et seuls les blocs
   situés sous la fenêtre au chargement reçoivent la classe d'attente. Sans JavaScript, ou si
   une étape échoue, tout le contenu reste visible. */
(function () {
  "use strict";

  var win = window;
  var doc = document;
  var root = doc.documentElement;

  function media(query) { return win.matchMedia ? win.matchMedia(query) : null; }
  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function store(key, value) {
    try {
      if (value === null) win.localStorage.removeItem(key);
      else win.localStorage.setItem(key, value);
    } catch (e) { /* stockage indisponible */ }
  }
  /* Lecture qui distingue « rien d'enregistré » de « stockage indisponible ». */
  function stored(key) {
    try { return { ok: true, value: win.localStorage.getItem(key) }; }
    catch (e) { return { ok: false, value: null }; }
  }

  var darkMq = media("(prefers-color-scheme: dark)");
  var calmMq = media("(prefers-reduced-motion: reduce)");
  var hoverMq = media("(hover: hover)");
  var fineMq = media("(hover: hover) and (pointer: fine)");

  /* Mouvement permis : ni le système ni le visiteur n'ont demandé moins d'animations. */
  function motionOn() {
    return root.getAttribute("data-motion") !== "off" && !(calmMq && calmMq.matches);
  }

  /* ---------- Thème clair / sombre ---------- */

  function currentTheme() {
    var t = root.getAttribute("data-theme");
    if (t === "light" || t === "dark") return t;
    return darkMq && darkMq.matches ? "dark" : "light";
  }

  /* Pendant la bascule, les transitions de couleur sont coupées (voir site.css) : boutons et liens
     changent de thème en même temps que le reste de la page. */
  function applyTheme(next) {
    root.setAttribute("data-theme-switching", "");
    if (next) root.setAttribute("data-theme", next);
    else root.removeAttribute("data-theme");
    win.requestAnimationFrame(function () {
      win.requestAnimationFrame(function () { root.removeAttribute("data-theme-switching"); });
    });
  }

  function setTheme(next) {
    applyTheme(next);
    store("theme", next);
  }

  each(doc.querySelectorAll("[data-theme-toggle]"), function (btn) {
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      /* Fondu enchaîné entre les deux thèmes quand le navigateur le permet. */
      if (motionOn() && typeof doc.startViewTransition === "function") {
        doc.startViewTransition(function () { setTheme(next); });
      } else {
        setTheme(next);
      }
    });
  });

  /* ---------- Apparition au défilement ---------- */

  var EDGE = 64;       /* px au-dessus du bas de la fenêtre : ligne de déclenchement */
  var STAGGER = 80;    /* ms entre deux blocs qui arrivent en même temps */
  var MAX_ORDER = 6;   /* au-delà, les blocs d'un même lot partent ensemble */
  var SETTLE = 2400;   /* ms : plus longue apparition définie dans site.css, marge comprise */
  var pending = [];
  var observer = null;

  /* État final : plus aucune classe ni délai, le bloc retrouve ses styles ordinaires. */
  function settle(el) {
    el.classList.remove("reveal-wait");
    el.classList.remove("reveal-in");
    el.style.removeProperty("--reveal-delay");
  }

  function release(el) {
    var i = pending.indexOf(el);
    if (i > -1) pending.splice(i, 1);
    if (observer) observer.unobserve(el);
  }

  function reveal(el, order) {
    var delay = Math.min(order, MAX_ORDER) * STAGGER;
    release(el);
    el.style.setProperty("--reveal-delay", delay + "ms");
    el.classList.add("reveal-in");
    startCounts(el, delay);
    win.setTimeout(function () { settle(el); }, SETTLE + delay);
  }

  function revealAll(animated) {
    pending.slice().forEach(function (el, k) {
      if (animated) {
        reveal(el, k);
      } else {
        release(el);
        settle(el);
      }
    });
  }

  /* Blocs sautés d'un coup (ancre, touche Fin, position restaurée) : visibles sans attendre. */
  function sweepAbove() {
    pending.slice().forEach(function (el) {
      if (el.getBoundingClientRect().bottom < 0) {
        release(el);
        settle(el);
      }
    });
  }

  /* Les blocs qui entrent ensemble partent en cascade, de haut en bas puis de gauche à droite. */
  function onIntersect(entries) {
    var hits = entries.filter(function (entry) { return entry.isIntersecting; });
    hits.sort(function (a, b) {
      return (a.boundingClientRect.top - b.boundingClientRect.top) ||
             (a.boundingClientRect.left - b.boundingClientRect.left);
    });
    hits.forEach(function (entry, k) { reveal(entry.target, k); });
    if (pending.length) sweepAbove();
  }

  function arm(el, line) {
    if (el.getBoundingClientRect().top > line) {
      el.classList.add("reveal-wait");
      pending.push(el);
      observer.observe(el);
    }
  }

  function initReveal() {
    /* Page enregistrée puis rouverte : des classes d'attente ou un chiffre arrêté en plein comptage
       peuvent traîner dans le code, on repart de zéro. */
    each(doc.querySelectorAll(".reveal-wait, .reveal-in"), settle);
    each(doc.querySelectorAll("[data-count]"), function (node) {
      node.removeAttribute("data-counting");
      node.removeAttribute("data-settling");
      node.textContent = countTarget(node);
    });
    var items = doc.querySelectorAll("[data-reveal]");
    if (!items.length || !motionOn() || !("IntersectionObserver" in win)) return;
    var line = win.innerHeight - EDGE;
    observer = new win.IntersectionObserver(onIntersect, { rootMargin: "0px 0px -" + EDGE + "px 0px" });
    each(items, function (el) {
      /* Bloc en colonnes CSS : on l'anime d'un seul tenant (rendu plus sûr qu'élément par élément) ;
         sur une seule colonne, chaque élément est une tuile qui se redresse à son tour. */
      if (el.getAttribute("data-reveal") === "cols" && win.getComputedStyle(el).columnCount === "auto") {
        each(el.children, function (child) {
          child.setAttribute("data-reveal", "tile");
          arm(child, line);
        });
      } else {
        arm(el, line);
      }
    });
  }

  /* ---------- En-tête : s'efface à la descente, revient à la remontée ---------- */

  var header = doc.querySelector(".site-header");
  var lastY = Math.max(win.pageYOffset || 0, 0);
  var queued = false;

  var keyboardNav = false;   /* vrai entre un appui sur Tab et le prochain geste au pointeur ou à la molette */

  /* L'en-tête qui revient peut passer devant une carte penchée : elle se remet droite d'abord. */
  function showHeader() {
    stopLeaning(true);
    if (header) header.classList.remove("is-hidden");
  }

  /* Retour immédiat, sans glissement : quand le focus va vers la barre, elle doit déjà être à l'écran,
     sinon le navigateur fait défiler la page pour aller chercher un lien encore hors champ. */
  function showHeaderNow() {
    if (!header || !header.classList.contains("is-hidden")) return;
    stopLeaning(true);
    header.style.transition = "none";
    header.classList.remove("is-hidden");
    void header.offsetHeight;
    header.style.transition = "";
  }

  /* La barre reste en place pendant une navigation au clavier ou sous le pointeur. Un clic ou un
     toucher laisse le focus dans la barre sans l'épingler : elle doit pouvoir s'effacer ensuite. */
  function headerPinned() {
    var keyboard;
    try { keyboard = !!header.querySelector(":focus-visible"); }
    catch (e) { keyboard = header.contains(doc.activeElement); }
    var hovered = !!(hoverMq && hoverMq.matches && header.matches && header.matches(":hover"));
    return keyboardNav || keyboard || hovered;
  }

  function onScroll() {
    queued = false;
    var y = Math.max(win.pageYOffset || 0, 0);
    /* Une carte penchée se remet droite d'un coup dès que la page défile. */
    stopLeaning(true);
    relightUnderPointer();
    /* Bas de page atteint : plus rien ne peut entrer dans la fenêtre, on montre ce qui attend encore. */
    if (pending.length && win.innerHeight + y >= root.scrollHeight - 2) revealAll(true);
    if (!header) return;
    if (!motionOn()) {
      showHeader();
      lastY = y;
      return;
    }
    var delta = y - lastY;
    if (Math.abs(delta) < 8) return;
    lastY = y;
    if (delta < 0 || y < 96) {
      showHeader();
    } else if (!headerPinned()) {
      header.classList.add("is-hidden");
    }
  }

  win.addEventListener("scroll", function () {
    if (queued) return;
    queued = true;
    win.requestAnimationFrame(onScroll);
  }, { passive: true });

  if (header) {
    header.addEventListener("focusin", showHeaderNow);
    /* Tab : l'appui précède le déplacement du focus, la barre est donc revenue avant qu'il n'arrive. */
    doc.addEventListener("keydown", function (event) {
      if (event.key === "Tab") {
        keyboardNav = true;
        showHeaderNow();
      }
    });
    ["pointerdown", "wheel", "touchstart"].forEach(function (type) {
      win.addEventListener(type, function () { keyboardNav = false; }, { passive: true });
    });
    showHeader();
  }

  /* ---------- Menu : rubrique en cours ---------- */

  function initSpy() {
    var nav = doc.querySelector(".site-nav");
    if (!nav || !("IntersectionObserver" in win)) return;
    var links = {};
    var current = null;
    var shown = null;

    function mark() {
      if (current === shown) return;
      shown = current;
      Object.keys(links).forEach(function (id) {
        if (id === current) links[id].setAttribute("aria-current", "location");
        else links[id].removeAttribute("aria-current");
      });
      /* Sur petit écran le menu défile horizontalement : le lien en cours reste en vue. */
      if (current && nav.scrollWidth > nav.clientWidth) {
        var link = links[current];
        var left = Math.max(0, link.offsetLeft - (nav.clientWidth - link.offsetWidth) / 2);
        if (typeof nav.scrollTo === "function") nav.scrollTo({ left: left, behavior: motionOn() ? "smooth" : "auto" });
        else nav.scrollLeft = left;
      }
    }

    /* Bande mince un peu au-dessus du milieu de la fenêtre : la rubrique qui la traverse est « en cours ». */
    var spy = new win.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) current = entry.target.id;
        else if (current === entry.target.id) current = null;
      });
      mark();
    }, { rootMargin: "-45% 0px -54% 0px" });

    each(nav.querySelectorAll('a[href^="#"]'), function (link) {
      var id = link.getAttribute("href").slice(1);
      var section = id ? doc.getElementById(id) : null;
      if (section) {
        links[id] = link;
        spy.observe(section);
      }
    });
  }

  /* ---------- Chiffres clés : ils comptent jusqu'à leur valeur ---------- */

  var COUNT_MS = 1200;
  var SETTLE_MS = 350;               /* resserrement des chiffres en fin de comptage (même durée dans site.css) */
  var ENTRANCE_COUNT_DELAY = 1100;   /* la bande des chiffres entre à 1 s (voir site.css) */
  var counters = [];                 /* une fonction par comptage en cours, qui pose la valeur finale */

  function grouped(digits, sep) {
    return sep ? digits.replace(/\B(?=(\d{3})+(?!\d))/g, sep) : digits;
  }

  /* La valeur à atteindre vient de la copie que le comptage ne touche jamais (celle des lecteurs d'écran). */
  function countTarget(node) {
    var source = node.parentNode ? node.parentNode.querySelector(".vh") : null;
    return source ? source.textContent : node.textContent;
  }

  /* Le texte visible est remplacé le temps du comptage, puis remis tel qu'il est dans la page.
     La valeur que lisent les lecteurs d'écran est ailleurs, dans un élément qui ne change pas. */
  function countUp(node, delay) {
    if (node.getAttribute("data-counting") || node.getAttribute("data-settling")) return;
    var final = countTarget(node);
    var parts = final.split(/(\d+(?:[\u202f\u00a0]\d{3})*)/);   /* textes et nombres, en alternance */
    if (parts.length < 2) return;
    var targets = parts.map(function (part, i) { return i % 2 ? parseInt(part.replace(/\D/g, ""), 10) : 0; });
    var seps = parts.map(function (part, i) { return i % 2 ? (part.match(/[\u202f\u00a0]/) || [""])[0] : ""; });
    var done = false;
    var settling = false;
    var start = null;

    function render(progress) {
      return parts.map(function (part, i) {
        return i % 2 ? grouped(String(Math.round(targets[i] * progress)), seps[i]) : part;
      }).join("");
    }
    /* Pose la valeur finale en texte simple. Appelée avec « true » à la fin naturelle du comptage, elle
       laisse d'abord les chiffres se resserrer ; sans argument (minuterie, impression, animations
       coupées), elle tranche tout de suite, où que l'on en soit. */
    function finish(settle) {
      if (done) return;
      if (settle === true && !settling && motionOn() && settleDigits()) return;
      done = true;
      node.textContent = final;
      node.removeAttribute("data-counting");
      node.removeAttribute("data-settling");
      var i = counters.indexOf(finish);
      if (i > -1) counters.splice(i, 1);
    }
    /* Pendant le comptage, les chiffres ont tous la même largeur (site.css, [data-counting]) : le nombre
       ne tremble pas. Au repos ils reprennent la leur, plus serrée. Pour passer de l'une à l'autre sans
       saut, chaque chiffre de la valeur finale est posé dans une case de l'ancienne largeur, que la
       feuille de style resserre ([data-settling]) ; le texte simple revient ensuite. */
    function settleDigits() {
      node.textContent = final;
      var first = final.search(/\d/);
      var range = doc.createRange();
      range.setStart(node.firstChild, first);
      range.setEnd(node.firstChild, first + 1);
      var cell = range.getBoundingClientRect().width;
      var digits = [];
      node.textContent = "";
      final.split(/(\d)/).forEach(function (piece) {
        if (!piece) return;
        if (!/^\d$/.test(piece)) {
          node.appendChild(doc.createTextNode(piece));
          return;
        }
        var span = doc.createElement("span");
        span.className = "digit";
        span.textContent = piece;
        node.appendChild(span);
        digits.push(span);
      });
      node.removeAttribute("data-counting");
      var own = digits.map(function (span) { return span.getBoundingClientRect().width; });
      if (!cell || !digits.length) return false;
      settling = true;
      digits.forEach(function (span) { span.style.width = cell + "px"; });
      void node.offsetWidth;
      node.setAttribute("data-settling", "1");
      digits.forEach(function (span, i) { span.style.width = own[i] + "px"; });
      win.setTimeout(finish, SETTLE_MS + 80);
      return true;
    }
    function frame(now) {
      if (done || settling) return;
      if (start === null) start = now;
      var t = Math.min((now - start) / COUNT_MS, 1);
      node.textContent = render(1 - Math.pow(1 - t, 3));
      if (t < 1) win.requestAnimationFrame(frame);
      else finish(true);
    }

    node.setAttribute("data-counting", "1");
    node.textContent = render(0);
    counters.push(finish);
    win.setTimeout(function () { win.requestAnimationFrame(frame); }, delay);
    /* Filet : la valeur finale est posée par une minuterie, même si les images d'animation ne viennent
       pas. Un comptage parti en retard (page ouverte dans un onglet d'arrière-plan, puis affichée) n'est
       pas coupé pour autant : le filet lui laisse le temps qui lui reste, compté depuis sa première image. */
    function safety() {
      if (done) return;
      var left = 0;
      if (start !== null && win.performance && win.performance.now) {
        left = COUNT_MS + SETTLE_MS + 500 - (win.performance.now() - start);
      }
      if (left > 0) win.setTimeout(safety, left);
      else finish();
    }
    win.setTimeout(safety, delay + COUNT_MS + SETTLE_MS + 500);
  }

  function startCounts(el, delay) {
    each(el.querySelectorAll("[data-count]"), function (node) { countUp(node, delay); });
  }

  function finishCounts() {
    counters.slice().forEach(function (finish) { finish(); });
  }

  /* Chiffres déjà dans le premier écran (fenêtre haute) : ils comptent pendant l'entrée de page.
     Ceux qui attendent plus bas compteront à leur apparition. */
  function initEntranceCounts() {
    if (root.classList.contains("entered") || !motionOn()) return;
    each(doc.querySelectorAll("[data-count]"), function (node) {
      if (node.closest && node.closest(".reveal-wait")) return;
      var box = node.getBoundingClientRect();
      if (box.bottom > 0 && box.top < win.innerHeight) countUp(node, ENTRANCE_COUNT_DELAY);
    });
  }

  /* ---------- Pointeur : lumière sur les tuiles, cartes qui penchent, lueur qui s'écarte ---------- */

  var TILES = ".case-card, .pager-link, .skill-group, .facts";
  var LEANERS = ".case-card, .pager-link";   /* cartes cliquables d'un seul tenant */
  var artPanels = doc.querySelectorAll(".art");
  var leaning = null;
  var pointer = null;
  var pointerQueued = false;

  /* Au repos, rien n'est en 3D. « D'un coup » : sans transition, quand la page défile ou que le
     mouvement est coupé, pour qu'une carte penchée ne passe jamais devant l'en-tête collant. */
  function stopLeaning(atOnce) {
    if (!leaning) return;
    var card = leaning;
    leaning = null;
    if (atOnce) {
      card.style.transition = "none";
      card.classList.remove("leaning");
      void card.offsetWidth;
      card.style.transition = "";
    } else {
      card.classList.remove("leaning");
    }
  }

  /* Place les deux lumières d'une tuile sous le pointeur ; rend sa position dans la tuile, de 0 à 1. */
  function lightTile(tile) {
    var box = tile.getBoundingClientRect();
    if (!box.width || !box.height) return null;
    var px = (pointer.x - box.left) / box.width;
    var py = (pointer.y - box.top) / box.height;
    tile.style.setProperty("--mx", (px * 100).toFixed(1) + "%");
    tile.style.setProperty("--my", (py * 100).toFixed(1) + "%");
    return { px: px, py: py, top: box.top };
  }

  function onPointer() {
    pointerQueued = false;
    if (!pointer || !(fineMq && fineMq.matches)) return;
    var moving = motionOn();
    if (moving) {
      var gx = (pointer.x / win.innerWidth - 0.5).toFixed(3);
      each(artPanels, function (panel) { panel.style.setProperty("--gx", gx); });
    }
    var tile = pointer.target && pointer.target.closest ? pointer.target.closest(TILES) : null;
    if (leaning && leaning !== tile) stopLeaning(false);
    if (!tile) return;
    var at = lightTile(tile);
    if (!at || !moving || !tile.matches(LEANERS)) return;
    /* Ni pendant une apparition, ni quand le haut de la carte passe sous l'en-tête collant (sa hauteur
       quand il est affiché : mesurée sans sa transition, il est collé en haut de la fenêtre). */
    var busy = tile.classList.contains("reveal-wait") || tile.classList.contains("reveal-in");
    var headerBottom = header && !header.classList.contains("is-hidden") ? header.offsetHeight : 0;
    if (busy || at.top < headerBottom) {
      if (leaning === tile) stopLeaning(true);
      return;
    }
    tile.style.setProperty("--lean-x", ((0.5 - at.py) * 5).toFixed(2) + "deg");
    tile.style.setProperty("--lean-y", ((at.px - 0.5) * 6).toFixed(2) + "deg");
    tile.classList.add("leaning");
    leaning = tile;
  }

  /* La page défile sous une souris immobile : la tuile qui arrive sous le pointeur est éclairée au bon
     endroit, sans attendre que la souris bouge. */
  function relightUnderPointer() {
    if (!pointer || !(fineMq && fineMq.matches) || !doc.elementFromPoint) return;
    var el = doc.elementFromPoint(pointer.x, pointer.y);
    var tile = el && el.closest ? el.closest(TILES) : null;
    if (tile) lightTile(tile);
  }

  doc.addEventListener("pointermove", function (event) {
    if (event.pointerType !== "mouse") return;
    pointer = { x: event.clientX, y: event.clientY, target: event.target };
    if (pointerQueued) return;
    pointerQueued = true;
    win.requestAnimationFrame(onPointer);
  }, { passive: true });
  /* La souris quitte la fenêtre : plus de position à suivre. */
  root.addEventListener("pointerleave", function () { pointer = null; });

  /* ---------- Bouton « Réduire les animations » ---------- */

  var motionButtons = doc.querySelectorAll("[data-motion-toggle]");

  function syncMotionButtons() {
    var pressed = root.getAttribute("data-motion") === "off" ? "true" : "false";
    each(motionButtons, function (btn) { btn.setAttribute("aria-pressed", pressed); });
  }

  /* Tout ce qui attendait une animation est montré tel quel : blocs, chiffres à leur valeur, cartes
     droites, lueur à sa place ; l'en-tête revient. */
  function calm() {
    revealAll(false);
    finishCounts();
    stopLeaning(true);
    each(artPanels, function (panel) { panel.style.removeProperty("--gx"); });
    showHeader();
  }

  /* L'entrée de page ne se joue qu'une fois (voir site.css) : une fois passée, ou dès que le mouvement
     est rétabli après coup, elle ne peut plus repartir. */
  function markEntered() { root.classList.add("entered"); }

  function setMotion(off) {
    if (off) {
      root.setAttribute("data-motion", "off");
      calm();
    } else {
      markEntered();
      root.removeAttribute("data-motion");
    }
    syncMotionButtons();
  }

  each(motionButtons, function (btn) {
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var off = root.getAttribute("data-motion") !== "off";
      setMotion(off);
      store("motion", off ? "off" : null);
    });
  });
  syncMotionButtons();

  /* Première image affichée, puis le temps de l'entrée la plus longue (lumière dans le titre : 3,1 s). */
  win.requestAnimationFrame(function () { win.setTimeout(markEntered, 3500); });

  if (calmMq) {
    var onCalmChange = function () {
      if (calmMq.matches) calm();
      else markEntered();
    };
    if (calmMq.addEventListener) calmMq.addEventListener("change", onCalmChange);
    else if (calmMq.addListener) calmMq.addListener(onCalmChange);
  }

  /* Page rendue par le cache de navigation (retour arrière), ou réglage changé dans un autre onglet :
     les deux préférences sont relues, pour que la page suive le dernier choix du visiteur. */
  function syncFromStore() {
    var theme = stored("theme");
    var motion = stored("motion");
    if (theme.ok) {
      var wanted = theme.value === "light" || theme.value === "dark" ? theme.value : null;
      if (root.getAttribute("data-theme") !== wanted) applyTheme(wanted);
    }
    if (motion.ok && (motion.value === "off") !== (root.getAttribute("data-motion") === "off")) {
      setMotion(motion.value === "off");
    }
  }

  win.addEventListener("pageshow", function (event) { if (event.persisted) syncFromStore(); });
  win.addEventListener("storage", function (event) {
    if (event.key === null || event.key === "theme" || event.key === "motion") syncFromStore();
  });

  /* À l'impression : tout est montré, les chiffres à leur valeur, les cartes droites. */
  win.addEventListener("beforeprint", function () {
    revealAll(false);
    finishCounts();
    stopLeaning(true);
  });

  initReveal();
  initEntranceCounts();
  initSpy();
})();
