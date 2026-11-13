# Architecture

FollowTheLyrics est une appli de bureau : un seul processus PyQt6, une fenêtre
transparente par-dessus le jeu, un panneau de contrôle et quelques fils de
travail. Le code est rangé **par responsabilité**. Une seule frontière est
abstraite : celle avec le système d'exploitation, parce qu'elle a plusieurs
implémentations (Windows, Linux, et un backend Qt seul pour macOS en
attendant le sien). Le reste n'a qu'une implémentation par besoin et reste
concret.

## La couche `desktop/`

`desktop/ports.py` décrit en `Protocol` tout ce que l'appli demande au système :
morceau en cours, capture audio, raccourcis globaux, fenêtres, programme au
premier plan, démarrage auto, raccourcis du bureau, boîtes de dialogue,
installation, format des releases. `desktop.current()` choisit un backend une
seule fois et renvoie un `Desktop` qui les regroupe.

- `desktop/windows/` : SMTC, WASAPI, `RegisterHotKey`, DWM, registre. Chaque
  module commence par `assert sys.platform == "win32"`, ce qui permet à mypy de
  vérifier le reste du code pour Linux sans voir ces appels.
- `desktop/linux/` : MPRIS par QtDBus pour le morceau en cours, PulseAudio ou
  PipeWire par `soundcard` pour la pulsation, X11 par `python-xlib` pour les
  raccourcis globaux et le programme au premier plan, XDG pour le démarrage
  auto et les raccourcis du bureau. Sous Wayland, `boot.prepare()` choisit
  XWayland quand il est là, seul moyen de garder l'overlay au-dessus. Sans
  serveur X, raccourcis et détection du jeu valent `None` ou restent neutres.
- `desktop/generic/` : uniquement Qt, pour macOS aujourd'hui. Les services
  sans équivalent portable valent `None` et l'interface masque ce qui en dépend (démarrage auto,
  installation, mises à jour) ou le signale (raccourcis globaux).

Ajouter un système, c'est écrire `desktop/<systeme>/backend.py` avec une
fonction `create()` qui remplit les ports qu'il sait servir. Aucun autre fichier
ne change.

## Paquets

```
src/followthelyrics/
├── __main__.py      point d'entrée : démarrage du backend puis app.main()
├── app.py           assemble tout : overlay, panneau, tray, minuteries, signaux
├── diagnostics.py   rapport de diagnostic et captures hors écran (--snapshot)
├── logs.py          journal tournant dans le dossier de données
├── version.py       version installée et dépôt GitHub
├── config/
│   ├── settings.py  dossier de données, config.json, valeurs par défaut
│   └── games.py     profils de jeux, zones interdites, captures
├── lyrics/
│   ├── model.py     Line : une ligne de paroles avec ses temps
│   ├── parsing.py   formats LRC et YRC, chanteurs, ad-libs, nettoyage des titres
│   ├── providers.py NetEase et LRCLIB, choix du meilleur résultat, traduction
│   ├── cache.py     cache disque des paroles trouvées ou introuvables
│   ├── analysis.py  refrains, mots forts, statistiques par mot
│   └── demo_song.py paroles de démonstration
├── desktop/
│   ├── ports.py     contrats avec le système d'exploitation
│   ├── windows/     backend Windows : SMTC, WASAPI, Win32, DWM, registre
│   ├── linux/       backend Linux : MPRIS, PulseAudio, X11, XDG
│   └── generic/     backend Qt seul, pour macOS
├── playback/
│   ├── track.py     NowPlaying : le morceau en cours
│   ├── sites.py     reconnaît le site du navigateur, ignore vidéos et streaming
│   ├── audio.py     choix de la sortie audio et détection des beats
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
    ├── startup.py   démarrage auto, raccourci du bureau, commande de lancement
    ├── install.py   installation, enregistrement, désinstallation
    ├── updater.py   recherche, téléchargement et remplacement du programme
    └── hotkeys.py   combinaisons de touches et gestionnaire de raccourcis
```

## Règles de dépendance

Chaque paquet n'importe que ce que liste ce tableau. Le graphe des modules n'a
aucun cycle.

| Paquet | Peut importer |
|---|---|
| `version`, `config` | rien d'interne |
| `lyrics` | `config.settings`, `version` |
| `playback` | `lyrics` |
| `desktop.ports` | `playback.track` |
| `desktop.windows`, `desktop.generic` | `desktop.ports`, `config.settings`, `playback.track` |
| `desktop.linux` | les mêmes, plus `desktop.generic` et `playback.sites` |
| `system` | `desktop.ports`, `config.settings`, `version` |
| `overlay` | `lyrics`, `config.settings` |
| `ui` | `config`, `desktop.ports`, `system`, `playback.sites`, `version`, jamais `overlay` |
| `app`, `diagnostics`, `__main__` | tout, dont `desktop` |

Deux conséquences utiles :

- `lyrics/` ne connaît ni Qt ni Windows. Tout le traitement des paroles se teste
  sur n'importe quelle machine.
- Seuls `desktop/windows/` et `desktop/linux/` parlent au système. Le reste reçoit les ports par son
  constructeur (`Overlay`, `MediaWorker`, `AudioBeats`, `Hotkeys`,
  `Installation`), ce qui permet de le tester avec de faux backends.
- Le panneau (`ui/`) ne touche jamais l'overlay directement : `app.py` lui passe
  l'objet et relaie les changements de réglages.

## Flux de données

```
MediaBackend ──▶ MediaWorker (QThread) ──signaux Qt──▶ App ──▶ Overlay
                    │                                 │
                    ├─ playback.sites (filtre)         └──▶ Panel
                    ├─ lyrics.cache
                    └─ lyrics.providers ──▶ lyrics.parsing

AudioBackend ──▶ playback.audio ──▶ BeatBridge ──beat──▶ Overlay.on_beat
HotkeyBackend ──▶ system.hotkeys.Hotkeys ──pressed──▶ App
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
- `ruff` (lint et format, 80 colonnes), `mypy` pour `win32` et pour `linux`, et
  `pytest` passent sans erreur ; la CI les lance à chaque pull request.
- Les attributs ne masquent jamais une méthode Qt (`size`, `style`, `layout`,
  `pos`…) : un widget qui garde un curseur l'appelle `size_slider`.
- Les données de l'utilisateur vont dans `settings.DATA_DIR` (surchargeable avec
  `FTL_DATA_DIR`, ce que font les tests).
