# Architecture

FollowTheLyrics est une appli de bureau Windows : un seul processus PyQt6,
une fenêtre transparente par-dessus le jeu, un panneau de contrôle et quelques
fils de travail. Le code est rangé **par responsabilité**, pas en couches
hexagonales : il n'y a qu'un seul « adaptateur » par besoin (une source de
musique, deux sources de paroles, une sortie écran), donc des ports abstraits
n'apporteraient que de l'indirection.

## Paquets

```
src/followthelyrics/
├── __main__.py      point d'entrée : démarrage blindé puis app.main()
├── app.py           assemble tout : overlay, panneau, tray, minuteries, signaux
├── diagnostics.py   rapport de diagnostic et captures hors écran (--snapshot)
├── logs.py          journal tournant dans le dossier de données
├── version.py       version installée et dépôt GitHub
├── config/
│   ├── settings.py  dossier de données, config.json, valeurs par défaut, démarrage auto
│   └── games.py     profils de jeux, zones interdites, captures
├── lyrics/
│   ├── model.py     Line : une ligne de paroles avec ses temps
│   ├── parsing.py   formats LRC et YRC, chanteurs, ad-libs, nettoyage des titres
│   ├── providers.py NetEase et LRCLIB, choix du meilleur résultat, traduction
│   ├── cache.py     cache disque des paroles trouvées ou introuvables
│   ├── analysis.py  refrains, mots forts, statistiques par mot
│   └── demo_song.py paroles de démonstration
├── playback/
│   ├── media.py     morceau en cours via SMTC (Windows Runtime)
│   ├── sites.py     reconnaît le site du navigateur, ignore vidéos et streaming
│   ├── audio.py     capture WASAPI et détection des beats
│   └── worker.py    fils Qt : MediaWorker (morceau, paroles, pochette), BeatBridge
├── overlay/
│   ├── window.py    la fenêtre des paroles : placement, animation, rendu
│   ├── effects.py   flou, palettes tirées de la pochette, accès aux pixels
│   ├── colors.py    couleurs LCH et regroupement des couleurs d'une image
│   ├── animation.py courbes d'animation
│   └── easter.py    spectacles déclenchés par certains morceaux
├── ui/
│   ├── panel.py     panneau de contrôle, une page par sujet
│   ├── widgets.py   briques animées partagées (cartes, interrupteurs, tuiles)
│   ├── welcome.py   écran de premier lancement
│   └── zone_editor.py éditeur des zones interdites d'un jeu
└── system/
    ├── win32.py     appels Win32 via ctypes, sans dépendance interne
    ├── bootstrap.py démarrage du .exe gelé, chargement des DLL
    ├── install.py   menu Démarrer, « Applications installées », désinstallation
    ├── updater.py   recherche, téléchargement et remplacement du .exe
    └── hotkeys.py   raccourcis clavier globaux
```

## Règles de dépendance

Chaque paquet n'importe que ce que liste ce tableau. Le graphe des modules n'a
aucun cycle.

| Paquet | Peut importer |
|---|---|
| `version`, `system.win32` | rien d'interne |
| `config` | `system.win32` |
| `lyrics` | `config.settings`, `version` |
| `system` | `config.settings`, `version` |
| `playback` | `lyrics` |
| `overlay` | `lyrics`, `config.settings`, `system.win32` |
| `ui` | `config`, `system`, `playback.sites`, `version`, jamais `overlay` |
| `app`, `diagnostics`, `__main__` | tout |

Deux conséquences utiles :

- `lyrics/` ne connaît ni Qt ni Windows. Tout le traitement des paroles se teste
  sur n'importe quelle machine.
- Le panneau (`ui/`) ne touche jamais l'overlay directement : `app.py` lui passe
  l'objet et relaie les changements de réglages.

## Flux de données

```
SMTC ──▶ playback.media ──▶ MediaWorker (QThread) ──signaux Qt──▶ App ──▶ Overlay
                                 │                                 │
                                 ├─ playback.sites (filtre)         └──▶ Panel
                                 ├─ lyrics.cache
                                 └─ lyrics.providers ──▶ lyrics.parsing

WASAPI ──▶ playback.audio ──▶ BeatBridge (QThread) ──beat──▶ Overlay.on_beat
Clavier ──▶ system.hotkeys (QThread) ──pressed──▶ App
```

- Les appels réseau, la lecture du morceau en cours et la capture audio vivent
  dans des `QThread`. Ils ne parlent au fil principal que par signaux Qt, donc
  aucun verrou n'est nécessaire.
- L'overlay ne se redessine que lorsque quelque chose bouge (`is_animating`) et
  ralentit sa minuterie au repos. Les mises en page de texte, les halos et les
  palettes sont mis en cache.

## Conventions

- Style Google : imports de modules seulement (`from followthelyrics.lyrics
  import parsing`, puis `parsing.parse_lrc(...)`), jamais d'import relatif.
- `ruff` (lint et format, 80 colonnes), `mypy` en mode `win32` et `pytest`
  passent sans erreur ; la CI les lance à chaque pull request.
- Les attributs ne masquent jamais une méthode Qt (`size`, `style`, `layout`,
  `pos`…) : un widget qui garde un curseur l'appelle `size_slider`.
- Les données de l'utilisateur vont dans `settings.DATA_DIR` (surchargeable avec
  `FTL_DATA_DIR`, ce que font les tests).
