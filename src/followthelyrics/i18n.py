LANGUAGES = {
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "zh": "中文",
}

DEFAULT = "en"

_ORDER = ("en", "es", "zh")

_state = {"lang": DEFAULT}


def set_language(code: str) -> None:
    _state["lang"] = code if code in LANGUAGES else DEFAULT


def language() -> str:
    return _state["lang"]


def translate_target() -> str:
    return "zh-CN" if _state["lang"] == "zh" else _state["lang"]


def tr(text: str) -> str:
    lang = _state["lang"]
    if lang == "fr":
        return text
    entry = TEXTS.get(text)
    return entry[_ORDER.index(lang)] if entry else text


TEXTS: dict[str, tuple[str, str, str]] = {
    "Accueil": (
        "Home",
        "Inicio",
        "首页",
    ),
    "Affichage": (
        "Display",
        "Pantalla",
        "显示",
    ),
    "Style": (
        "Style",
        "Estilo",
        "样式",
    ),
    "Musique": (
        "Music",
        "Música",
        "音乐",
    ),
    "Jeux": (
        "Games",
        "Juegos",
        "游戏",
    ),
    "Raccourcis": (
        "Shortcuts",
        "Atajos",
        "快捷键",
    ),
    "Général": (
        "General",
        "General",
        "通用",
    ),
    "Ce qui joue, et l'essentiel à portée de main.": (
        "What's playing, and the essentials at hand.",
        "Lo que suena y lo esencial a mano.",
        "正在播放的内容和常用设置。",
    ),
    "Où et comment les paroles s'affichent.": (
        "Where and how the lyrics appear.",
        "Dónde y cómo aparece la letra.",
        "歌词显示的位置和方式。",
    ),
    "Couleurs, animation et police.": (
        "Colours, animation and font.",
        "Colores, animación y fuente.",
        "颜色、动画和字体。",
    ),
    "Sources, traduction et calage.": (
        "Sources, translation and timing.",
        "Fuentes, traducción y sincronía.",
        "来源、翻译和同步。",
    ),
    "Les zones que les paroles évitent.": (
        "The areas the lyrics stay out of.",
        "Las zonas que la letra evita.",
        "歌词会避开的区域。",
    ),
    "Ils marchent même en pleine partie.": (
        "They work even mid-game.",
        "Funcionan incluso en plena partida.",
        "游戏中也能使用。",
    ),
    "Démarrage, mises à jour, à propos.": (
        "Startup, updates, about.",
        "Inicio, actualizaciones, acerca de.",
        "启动、更新、关于。",
    ),
    "En cours": (
        "Playing",
        "Sonando",
        "播放中",
    ),
    "En pause": (
        "Paused",
        "En pausa",
        "已暂停",
    ),
    "En attente": (
        "Waiting",
        "En espera",
        "等待中",
    ),
    "En attente…": (
        "Waiting…",
        "En espera…",
        "等待中…",
    ),
    "Aucune musique": (
        "No music",
        "Sin música",
        "没有音乐",
    ),
    "Lance un morceau sur Spotify, YouTube Music, Deezer… les paroles arrivent toutes seules.": (
        "Play a track on Spotify, YouTube Music, Deezer… the lyrics show up on their own.",
        "Pon una canción en Spotify, YouTube Music, Deezer… la letra aparece sola.",
        "在 Spotify、YouTube Music、Deezer 等播放歌曲，歌词会自动出现。",
    ),
    "Recherche des paroles…": (
        "Looking for lyrics…",
        "Buscando la letra…",
        "正在查找歌词…",
    ),
    "Pas de paroles synchronisées pour ce titre.": (
        "No synced lyrics for this track.",
        "No hay letra sincronizada para este tema.",
        "这首歌没有同步歌词。",
    ),
    "Jeu détecté": (
        "Detected game",
        "Juego detectado",
        "检测到的游戏",
    ),
    "JEU DÉTECTÉ": (
        "Detected game",
        "Juego detectado",
        "检测到的游戏",
    ),
    "Bureau": (
        "Desktop",
        "Escritorio",
        "桌面",
    ),
    "Mode d'affichage": (
        "Display mode",
        "Modo de visualización",
        "显示模式",
    ),
    "Essayer sans musique": (
        "Try without music",
        "Probar sin música",
        "无音乐试用",
    ),
    "Des paroles de démonstration, pour régler le style.": (
        "Demo lyrics, to tune the style.",
        "Letra de demostración, para ajustar el estilo.",
        "演示歌词，方便调整样式。",
    ),
    "Album": (
        "Album",
        "Álbum",
        "专辑",
    ),
    "Blanc": (
        "White",
        "Blanco",
        "白色",
    ),
    "Paroles affichées": (
        "Lyrics shown",
        "Letra visible",
        "歌词已显示",
    ),
    "Paroles masquées": (
        "Lyrics hidden",
        "Letra oculta",
        "歌词已隐藏",
    ),
    "Affichées": (
        "Shown",
        "Visible",
        "已显示",
    ),
    "Masquées": (
        "Hidden",
        "Oculta",
        "已隐藏",
    ),
    "Plein écran exclusif détecté : les paroles ne peuvent pas passer par-dessus le jeu. ": (
        "Exclusive fullscreen detected: the lyrics cannot show over the game. ",
        "Pantalla completa exclusiva detectada: la letra no puede mostrarse sobre el juego. ",
        "检测到独占全屏：歌词无法显示在游戏上方。",
    ),
    "Mode": (
        "Mode",
        "Modo",
        "模式",
    ),
    "Passe la souris sur une carte pour voir le mode en action.": (
        "Hover a card to see the mode in action.",
        "Pasa el ratón por una tarjeta para ver el modo en acción.",
        "将鼠标移到卡片上可预览该模式。",
    ),
    "Classique": (
        "Classic",
        "Clásico",
        "经典",
    ),
    "Les lignes défilent dans un coin, comme sur Spotify.": (
        "Lines scroll in a corner, like on Spotify.",
        "Las líneas pasan en una esquina, como en Spotify.",
        "歌词在角落滚动，像 Spotify 一样。",
    ),
    "Edit": (
        "Edit",
        "Edit",
        "Edit",
    ),
    "Chaque ligne surgit à un endroit différent de l'écran.": (
        "Each line pops up at a different spot on screen.",
        "Cada línea aparece en un lugar distinto de la pantalla.",
        "每行歌词出现在屏幕的不同位置。",
    ),
    "Machine à écrire": (
        "Typewriter",
        "Máquina de escribir",
        "打字机",
    ),
    "Les lettres s'écrivent au fil du chant.": (
        "Letters are typed as they are sung.",
        "Las letras se escriben al ritmo del canto.",
        "文字随演唱逐个打出。",
    ),
    "Placement et taille": (
        "Placement and size",
        "Posición y tamaño",
        "位置和大小",
    ),
    "Position": (
        "Position",
        "Posición",
        "位置",
    ),
    "En haut de l'écran : à gauche, au centre ou à droite.": (
        "At the top of the screen: left, centre or right.",
        "En la parte superior: izquierda, centro o derecha.",
        "屏幕顶部：左、中或右。",
    ),
    "Gauche": (
        "Left",
        "Izquierda",
        "左",
    ),
    "Centre": (
        "Centre",
        "Centro",
        "中",
    ),
    "Droite": (
        "Right",
        "Derecha",
        "右",
    ),
    "Taille du texte": (
        "Text size",
        "Tamaño del texto",
        "文字大小",
    ),
    "Moments forts": (
        "Highlights",
        "Momentos clave",
        "高光时刻",
    ),
    "Titre en géant": (
        "Giant title",
        "Título gigante",
        "超大歌名",
    ),
    "Quand le chanteur dit le titre du morceau, il s'affiche en très grand (en jeu : dans un espace libre, jamais sur l'action).": (
        "When the singer says the track's title, it shows very large (in game: in a free area, never over the action).",
        "Cuando el cantante dice el título, aparece muy grande (en el juego: en un espacio libre, nunca sobre la acción).",
        "当歌手唱到歌名时，以超大字体显示（游戏中只出现在空白区域，不会挡住操作）。",
    ),
    "Toujours": (
        "Always",
        "Siempre",
        "始终",
    ),
    "Hors jeu": (
        "Out of game",
        "Fuera del juego",
        "非游戏时",
    ),
    "Jamais": (
        "Never",
        "Nunca",
        "从不",
    ),
    "Carte de la pochette": (
        "Cover card",
        "Tarjeta de portada",
        "封面卡片",
    ),
    "Pochette, titre et artiste quelques secondes au début du morceau.": (
        "Cover, title and artist for a few seconds at the start of the track.",
        "Portada, título y artista unos segundos al empezar el tema.",
        "歌曲开始时显示几秒封面、歌名和歌手。",
    ),
    "Aperçu": (
        "Preview",
        "Vista previa",
        "预览",
    ),
    "Les paroles prennent vie": (
        "Lyrics come alive",
        "La letra cobra vida",
        "让歌词活起来",
    ),
    "Couleurs du texte": (
        "Text colours",
        "Colores del texto",
        "文字颜色",
    ),
    "Couleurs de l'album": (
        "Album colours",
        "Colores del álbum",
        "专辑配色",
    ),
    "Tirées de la pochette du morceau.": (
        "Taken from the track's cover.",
        "Sacados de la portada del tema.",
        "取自歌曲封面。",
    ),
    "Blanc lumineux": (
        "Bright white",
        "Blanco brillante",
        "亮白",
    ),
    "Blanc avec un léger halo.": (
        "White with a soft glow.",
        "Blanco con un halo suave.",
        "白色带柔和光晕。",
    ),
    "Paroles": (
        "Lyrics",
        "Letra",
        "歌词",
    ),
    "Animation": (
        "Animation",
        "Animación",
        "动画",
    ),
    "Arrivée des mots": (
        "Word entrance",
        "Entrada de las palabras",
        "文字出现方式",
    ),
    "Pour les modes Classique et Edit.": (
        "For Classic and Edit modes.",
        "Para los modos Clásico y Edit.",
        "适用于经典和 Edit 模式。",
    ),
    "Cinétique": (
        "Kinetic",
        "Cinético",
        "动感",
    ),
    "Karaoké": (
        "Karaoke",
        "Karaoke",
        "卡拉OK",
    ),
    "Simple": (
        "Simple",
        "Simple",
        "简洁",
    ),
    "Pulsation sur le beat": (
        "Pulse on the beat",
        "Pulso con el ritmo",
        "随节拍律动",
    ),
    "Le texte grossit légèrement sur la grosse caisse.": (
        "The text swells slightly on the kick drum.",
        "El texto crece un poco con el bombo.",
        "文字随底鼓轻微放大。",
    ),
    "Particules sur les mots tenus": (
        "Particles on held words",
        "Partículas en las notas largas",
        "长音粒子效果",
    ),
    "De petites étincelles quand le chanteur tient une note.": (
        "Small sparks when the singer holds a note.",
        "Pequeñas chispas cuando el cantante sostiene una nota.",
        "歌手拖长音时出现小火花。",
    ),
    "Mots empilés": (
        "Stacked words",
        "Palabras apiladas",
        "文字堆叠",
    ),
    "En mode Edit, des rangées de tailles différentes, la plus forte en couleur.": (
        "In Edit mode, rows of different sizes, the strongest one in colour.",
        "En modo Edit, filas de distintos tamaños, la más fuerte en color.",
        "Edit 模式下各行大小不同，最重要的一行带颜色。",
    ),
    "Effet 3D sur les côtés": (
        "3D effect on the sides",
        "Efecto 3D en los lados",
        "两侧 3D 效果",
    ),
    "En mode Edit, les lignes à gauche et à droite partent en perspective.": (
        "In Edit mode, lines on the left and right tilt in perspective.",
        "En modo Edit, las líneas a izquierda y derecha se inclinan en perspectiva.",
        "Edit 模式下左右两侧的歌词带透视倾斜。",
    ),
    "Easter eggs": (
        "Easter eggs",
        "Easter eggs",
        "彩蛋",
    ),
    "Quelques morceaux cachent un spectacle spécial. À toi de les trouver.": (
        "A few tracks hide a special show. Yours to find.",
        "Algunos temas esconden un espectáculo especial. Te toca encontrarlos.",
        "有些歌曲藏着特别的演出，等你发现。",
    ),
    "Police": (
        "Font",
        "Fuente",
        "字体",
    ),
    "Rechercher une police…": (
        "Search a font…",
        "Buscar una fuente…",
        "搜索字体…",
    ),
    "Recommandées": (
        "Recommended",
        "Recomendadas",
        "推荐",
    ),
    "Toutes les polices": (
        "All fonts",
        "Todas las fuentes",
        "所有字体",
    ),
    "Applis écoutées": (
        "Apps followed",
        "Apps seguidas",
        "监听的应用",
    ),
    "Décoche celles qui ne servent pas à la musique. Les médias de plus de 20 minutes sont toujours ignorés.": (
        "Untick the ones you don't use for music. Media longer than 20 minutes is always ignored.",
        "Desmarca las que no usas para música. Los contenidos de más de 20 minutos siempre se ignoran.",
        "取消勾选不用来听音乐的应用。超过 20 分钟的媒体始终忽略。",
    ),
    "Aucune appli détectée pour l'instant. Lance une musique.": (
        "No app detected yet. Play some music.",
        "Ninguna app detectada por ahora. Pon música.",
        "尚未检测到应用。请播放音乐。",
    ),
    "Sites de musique dans le navigateur": (
        "Music sites in the browser",
        "Sitios de música en el navegador",
        "浏览器中的音乐网站",
    ),
    "Quand le son vient de Chrome, Opera, Brave, Edge, Firefox… seuls ces sites affichent des paroles. Netflix, Twitch et les autres vidéos sont ignorés.": (
        "When the sound comes from Chrome, Opera, Brave, Edge, Firefox… only these sites show lyrics. Netflix, Twitch and other videos are ignored.",
        "Cuando el sonido viene de Chrome, Opera, Brave, Edge, Firefox… solo estos sitios muestran letra. Netflix, Twitch y otros vídeos se ignoran.",
        "当声音来自 Chrome、Opera、Brave、Edge、Firefox 等浏览器时，只有这些网站会显示歌词。Netflix、Twitch 和其他视频会被忽略。",
    ),
    "En ce moment — ": (
        "Right now — ",
        "Ahora mismo — ",
        "当前 — ",
    ),
    "{} : site non reconnu, ": (
        "{}: unrecognised site, ",
        "{}: sitio no reconocido, ",
        "{}：未识别的网站，",
    ),
    "suivi quand même": (
        "followed anyway",
        "seguido igualmente",
        "仍然跟随",
    ),
    "ignoré": (
        "ignored",
        "ignorado",
        "已忽略",
    ),
    ", ignoré": (
        ", ignored",
        ", ignorado",
        "，已忽略",
    ),
    "Tous les autres sites": (
        "All other sites",
        "Todos los demás sitios",
        "所有其他网站",
    ),
    "À activer seulement si ta musique vient d'un site absent de la liste : les vidéos seront de nouveau suivies.": (
        "Turn on only if your music comes from a site that's not listed: videos will be followed again.",
        "Actívalo solo si tu música viene de un sitio que no está en la lista: los vídeos volverán a seguirse.",
        "仅当你的音乐来自列表之外的网站时开启：视频也会重新被跟随。",
    ),
    "Traduction en français": (
        "Lyrics translation",
        "Traducción de la letra",
        "歌词翻译",
    ),
    "Sous la ligne, pour les chansons qui ne sont pas en français.": (
        "Under the line, for songs in another language.",
        "Bajo la línea, para canciones en otro idioma.",
        "显示在歌词下方，适用于其他语言的歌曲。",
    ),
    "Plus de mot à mot (LiriQo)": (
        "More word-by-word (LiriQo)",
        "Más palabra a palabra (LiriQo)",
        "更多逐字歌词（LiriQo）",
    ),
    "Quand un morceau n'a pas de mot à mot, demande à LiriQo, un service tiers qui regroupe d'autres sources. Le titre et l'artiste lui sont envoyés.": (
        "When a track has no word-by-word timing, ask LiriQo, a third-party service that gathers other sources. The title and artist are sent to it.",
        "Cuando un tema no tiene palabra a palabra, se consulta a LiriQo, un servicio externo que reúne otras fuentes. Se le envían el título y el artista.",
        "当歌曲没有逐字歌词时，向第三方服务 LiriQo 查询，它汇集了其他来源。歌名和歌手会发送给它。",
    ),
    "Calage des paroles": (
        "Lyrics timing",
        "Sincronía de la letra",
        "歌词同步",
    ),
    "Remettre à zéro": (
        "Reset",
        "Restablecer",
        "重置",
    ),
    "Paroles en retard : appuie sur +. En avance : appuie sur −.": (
        "Lyrics late: press +. Early: press −.",
        "Letra atrasada: pulsa +. Adelantada: pulsa −.",
        "歌词慢了按 +，快了按 −。",
    ),
    "Les paroles contournent les zones importantes du jeu : vie, minimap, score, sorts…": (
        "Lyrics stay clear of the game's important areas: health, minimap, score, abilities…",
        "La letra evita las zonas importantes del juego: vida, minimapa, marcador, habilidades…",
        "歌词会避开游戏的重要区域：血量、小地图、比分、技能等。",
    ),
    "Zones à éviter": (
        "Areas to avoid",
        "Zonas a evitar",
        "避让区域",
    ),
    "Voir les zones 5 secondes": (
        "Show the zones for 5 seconds",
        "Ver las zonas 5 segundos",
        "显示区域 5 秒",
    ),
    "Dessiner les zones…": (
        "Draw the zones…",
        "Dibujar las zonas…",
        "绘制区域…",
    ),
    "Ajouter un jeu en 3 étapes": (
        "Add a game in 3 steps",
        "Añadir un juego en 3 pasos",
        "三步添加游戏",
    ),
    "Dans le jeu, appuie sur {} : une capture est prise, sans les paroles.": (
        "In the game, press {}: a capture is taken, without the lyrics.",
        "En el juego, pulsa {}: se toma una captura, sin la letra.",
        "在游戏中按 {}：会截取一张不含歌词的画面。",
    ),
    "Reviens ici : la capture s'ouvre toute seule. Dessine à la souris un rectangle sur chaque endroit à protéger.": (
        "Come back here: the capture opens by itself. Draw a rectangle with the mouse over each spot to protect.",
        "Vuelve aquí: la captura se abre sola. Dibuja con el ratón un rectángulo sobre cada zona a proteger.",
        "回到这里：截图会自动打开。用鼠标在每个需要保护的位置画一个矩形。",
    ),
    "Clique sur « Enregistrer ». C'est appliqué tout de suite, sans relancer le jeu.": (
        "Click “Save”. It applies right away, without restarting the game.",
        "Haz clic en «Guardar». Se aplica al instante, sin reiniciar el juego.",
        "点击“保存”。立即生效，无需重启游戏。",
    ),
    "Donne d'abord un raccourci à « Capturer le jeu » dans la page Raccourcis.": (
        "First give “Capture the game” a shortcut in the Shortcuts page.",
        "Primero asigna un atajo a «Capturar el juego» en la página Atajos.",
        "请先在“快捷键”页为“截取游戏画面”设置快捷键。",
    ),
    "Le jeu cache les paroles ?": (
        "The game hides the lyrics?",
        "¿El juego tapa la letra?",
        "游戏挡住了歌词？",
    ),
    "Mets tes jeux en « fenêtré sans bordure » dans leurs options vidéo. En plein écran exclusif, {} n'affiche aucune fenêtre par-dessus le jeu.": (
        "Set your games to “borderless windowed” in their video options. In exclusive fullscreen, {} shows no window over the game.",
        "Pon tus juegos en «ventana sin bordes» en sus opciones de vídeo. En pantalla completa exclusiva, {} no muestra ninguna ventana sobre el juego.",
        "请在游戏的视频选项中设为“无边框窗口”。独占全屏时，{} 不会在游戏上方显示任何窗口。",
    ),
    "Autres jeux en plein écran": (
        "Other fullscreen games",
        "Otros juegos a pantalla completa",
        "其他全屏游戏",
    ),
    "Jeu inconnu (plein ecran)": (
        "Unknown game (fullscreen)",
        "Juego desconocido (pantalla completa)",
        "未知游戏（全屏）",
    ),
    "Passe le jeu en « fenêtré sans bordure » dans ses options vidéo.": (
        "Set the game to “borderless windowed” in its video options.",
        "Pon el juego en «ventana sin bordes» en sus opciones de vídeo.",
        "请在游戏的视频选项中设为“无边框窗口”。",
    ),
    "Tes raccourcis": (
        "Your shortcuts",
        "Tus atajos",
        "你的快捷键",
    ),
    "Clique sur un raccourci, puis appuie sur la nouvelle combinaison (avec Ctrl ou Alt, ou une touche F1 à F24). Échap annule, Suppr retire le raccourci.": (
        "Click a shortcut, then press the new combination (with Ctrl or Alt, or an F1 to F24 key). Esc cancels, Delete removes the shortcut.",
        "Haz clic en un atajo y pulsa la nueva combinación (con Ctrl o Alt, o una tecla F1 a F24). Esc cancela, Supr quita el atajo.",
        "点击某个快捷键，然后按下新的组合键（需含 Ctrl 或 Alt，或 F1 至 F24）。Esc 取消，Delete 清除快捷键。",
    ),
    "Remettre les raccourcis d'origine": (
        "Restore default shortcuts",
        "Restaurar los atajos originales",
        "恢复默认快捷键",
    ),
    "Afficher / masquer les paroles": (
        "Show / hide the lyrics",
        "Mostrar / ocultar la letra",
        "显示 / 隐藏歌词",
    ),
    "Changer de mode d'affichage": (
        "Change display mode",
        "Cambiar el modo de visualización",
        "切换显示模式",
    ),
    "Couleurs de l'album / blanc": (
        "Album colours / white",
        "Colores del álbum / blanco",
        "专辑配色 / 白色",
    ),
    "Changer d'animation": (
        "Change animation",
        "Cambiar la animación",
        "切换动画",
    ),
    "Paroles plus tôt (+0,2 s)": (
        "Lyrics earlier (+0.2 s)",
        "Letra antes (+0,2 s)",
        "歌词提前（+0.2 秒）",
    ),
    "Paroles plus tard (−0,2 s)": (
        "Lyrics later (−0.2 s)",
        "Letra después (−0,2 s)",
        "歌词延后（−0.2 秒）",
    ),
    "Voir les zones du jeu (5 s)": (
        "Show the game's zones (5 s)",
        "Ver las zonas del juego (5 s)",
        "显示游戏区域（5 秒）",
    ),
    "Capturer le jeu pour dessiner les zones": (
        "Capture the game to draw the zones",
        "Capturar el juego para dibujar las zonas",
        "截取游戏画面以绘制区域",
    ),
    "Appuie sur les touches…": (
        "Press the keys…",
        "Pulsa las teclas…",
        "请按键…",
    ),
    "Ajoute Ctrl ou Alt": (
        "Add Ctrl or Alt",
        "Añade Ctrl o Alt",
        "请加上 Ctrl 或 Alt",
    ),
    "Aucun · clique pour choisir": (
        "None · click to choose",
        "Ninguno · haz clic para elegir",
        "无 · 点击设置",
    ),
    "Modifier": (
        "Change",
        "Cambiar",
        "修改",
    ),
    "aucun raccourci": (
        "no shortcut",
        "sin atajo",
        "无快捷键",
    ),
    "« {} » utilisait déjà {} : ce raccourci lui a été retiré.": (
        "“{}” was already using {}: that shortcut was removed from it.",
        "«{}» ya usaba {}: se le ha quitado ese atajo.",
        "“{}”原本使用 {}：已移除它的该快捷键。",
    ),
    " : cette combinaison est déjà prise par une autre appli. Choisis-en une autre.": (
        ": this combination is already taken by another app. Pick another one.",
        ": esta combinación ya la usa otra app. Elige otra.",
        "：此组合键已被其他应用占用，请换一个。",
    ),
    "{} refuse ": (
        "{} refuses ",
        "{} rechaza ",
        "{} 拒绝了 ",
    ),
    "\nEn jeu : {} et {}.": (
        "\nIn game: {} and {}.",
        "\nEn el juego: {} y {}.",
        "\n游戏中：{} 和 {}。",
    ),
    "Les raccourcis clavier globaux ne sont pas encore disponibles sur {}.": (
        "Global keyboard shortcuts are not available on {} yet.",
        "Los atajos de teclado globales aún no están disponibles en {}.",
        "全局快捷键暂不支持 {}。",
    ),
    "Démarrage": (
        "Startup",
        "Inicio",
        "启动",
    ),
    "Lancer avec {}": (
        "Start with {}",
        "Iniciar con {}",
        "随 {} 启动",
    ),
    "Démarre tout seul à l'allumage du PC, discrètement près de l'heure.": (
        "Starts by itself when the PC boots, quietly near the clock.",
        "Arranca solo al encender el PC, discretamente junto al reloj.",
        "开机自动启动，安静地待在时钟旁。",
    ),
    "Langue": (
        "Language",
        "Idioma",
        "语言",
    ),
    "Langue de l'appli": (
        "App language",
        "Idioma de la app",
        "应用语言",
    ),
    "Installation": (
        "Installation",
        "Instalación",
        "安装",
    ),
    "Installée sur ce PC": (
        "Installed on this PC",
        "Instalada en este PC",
        "已安装到此电脑",
    ),
    "Désinstaller": (
        "Uninstall",
        "Desinstalar",
        "卸载",
    ),
    "L'appli est dans le menu Démarrer et dans les applications installées de {}.": (
        "The app is in the Start menu and in {}'s installed apps.",
        "La app está en el menú Inicio y en las aplicaciones instaladas de {}.",
        "应用已出现在开始菜单和 {} 的已安装应用中。",
    ),
    "Installer sur ce PC": (
        "Install on this PC",
        "Instalar en este PC",
        "安装到此电脑",
    ),
    "Installer": (
        "Install",
        "Instalar",
        "安装",
    ),
    "Range l'appli à sa place avec une icône dans le menu Démarrer. Tu pourras ensuite jeter le fichier téléchargé.": (
        "Puts the app in its place with a Start menu icon. You can then delete the downloaded file.",
        "Coloca la app en su sitio con un icono en el menú Inicio. Luego puedes borrar el archivo descargado.",
        "把应用安装到位并在开始菜单添加图标。之后可以删除下载的文件。",
    ),
    "Mises à jour": (
        "Updates",
        "Actualizaciones",
        "更新",
    ),
    "Version {}": (
        "Version {}",
        "Versión {}",
        "版本 {}",
    ),
    "Rechercher une mise à jour": (
        "Check for updates",
        "Buscar actualizaciones",
        "检查更新",
    ),
    "L'appli vérifie toute seule de temps en temps et te prévient ici.": (
        "The app checks by itself from time to time and tells you here.",
        "La app comprueba sola de vez en cuando y te avisa aquí.",
        "应用会不时自动检查，并在此处提醒你。",
    ),
    "Recherche…": (
        "Checking…",
        "Buscando…",
        "正在检查…",
    ),
    "Tu as déjà la dernière version.": (
        "You already have the latest version.",
        "Ya tienes la última versión.",
        "已是最新版本。",
    ),
    "Impossible de joindre GitHub. Vérifie ta connexion.": (
        "Can't reach GitHub. Check your connection.",
        "No se puede conectar con GitHub. Revisa tu conexión.",
        "无法连接 GitHub，请检查网络。",
    ),
    "La version {} est disponible (bandeau en haut).": (
        "Version {} is available (banner at the top).",
        "La versión {} está disponible (aviso arriba).",
        "版本 {} 已发布（见顶部提示）。",
    ),
    "La version {} est disponible. La mise à jour se fait toute seule, en gardant tes réglages.": (
        "Version {} is available. The update installs by itself and keeps your settings.",
        "La versión {} está disponible. La actualización se hace sola y conserva tus ajustes.",
        "版本 {} 已发布。更新会自动完成并保留你的设置。",
    ),
    "Mettre à jour": (
        "Update",
        "Actualizar",
        "更新",
    ),
    "Téléchargement…": (
        "Downloading…",
        "Descargando…",
        "正在下载…",
    ),
    "Téléchargement {} %": (
        "Downloading {} %",
        "Descargando {} %",
        "正在下载 {} %",
    ),
    "Installation… l'appli va redémarrer toute seule.": (
        "Installing… the app will restart by itself.",
        "Instalando… la app se reiniciará sola.",
        "正在安装…应用会自动重启。",
    ),
    "Réessayer": (
        "Retry",
        "Reintentar",
        "重试",
    ),
    "À propos": (
        "About",
        "Acerca de",
        "关于",
    ),
    "Ouvrir le site": (
        "Open the website",
        "Abrir el sitio web",
        "打开网站",
    ),
    "GitHub de War3l": (
        "War3l's GitHub",
        "GitHub de War3l",
        "War3l 的 GitHub",
    ),
    "Les paroles de ta musique, par-dessus tes jeux. Gratuit et libre. Créé par War3l.": (
        "Your music's lyrics, right over your games. Free and open source. Made by War3l.",
        "La letra de tu música, sobre tus juegos. Gratis y libre. Creado por War3l.",
        "你的音乐歌词，显示在游戏之上。免费开源。由 War3l 制作。",
    ),
    "Toujours actif. Clique sur l'icône près de l'heure pour rouvrir le panneau.": (
        "Still running. Click the icon near the clock to reopen the panel.",
        "Sigue activo. Haz clic en el icono junto al reloj para reabrir el panel.",
        "仍在运行。点击时钟旁的图标可重新打开面板。",
    ),
    "Ouvrir le panneau": (
        "Open the panel",
        "Abrir el panel",
        "打开面板",
    ),
    "Masquer les paroles": (
        "Hide the lyrics",
        "Ocultar la letra",
        "隐藏歌词",
    ),
    "Afficher les paroles": (
        "Show the lyrics",
        "Mostrar la letra",
        "显示歌词",
    ),
    "Quitter": (
        "Quit",
        "Salir",
        "退出",
    ),
    "Paroles affichees": (
        "Lyrics shown",
        "Letra visible",
        "歌词已显示",
    ),
    "Paroles masquees": (
        "Lyrics hidden",
        "Letra oculta",
        "歌词已隐藏",
    ),
    "Mode : {}": (
        "Mode: {}",
        "Modo: {}",
        "模式：{}",
    ),
    "Animation : {}": (
        "Animation: {}",
        "Animación: {}",
        "动画：{}",
    ),
    "Decalage : {} s": (
        "Offset: {} s",
        "Desfase: {} s",
        "偏移：{} 秒",
    ),
    "Zones : {}": (
        "Zones: {}",
        "Zonas: {}",
        "区域：{}",
    ),
    "Capture impossible": (
        "Capture failed",
        "Captura imposible",
        "截图失败",
    ),
    "Capture prise : reviens sur FollowTheLyrics pour dessiner les zones": (
        "Capture taken: go back to FollowTheLyrics to draw the zones",
        "Captura tomada: vuelve a FollowTheLyrics para dibujar las zonas",
        "已截图：回到 FollowTheLyrics 绘制区域",
    ),
    "Mets-toi dans le jeu, puis ": (
        "Go into the game, then ",
        "Entra en el juego y luego ",
        "请进入游戏，然后 ",
    ),
    "Elles s'affichent sur ton autre écran. ": (
        "They are shown on your other screen. ",
        "Se muestran en tu otra pantalla. ",
        "歌词会显示在你的另一块屏幕上。",
    ),
    "FollowTheLyrics : jeu en plein écran exclusif": (
        "FollowTheLyrics: game in exclusive fullscreen",
        "FollowTheLyrics: juego en pantalla completa exclusiva",
        "FollowTheLyrics：游戏处于独占全屏",
    ),
    "Les paroles ne peuvent pas s'afficher par-dessus. ": (
        "The lyrics cannot show over it. ",
        "La letra no puede mostrarse encima. ",
        "歌词无法显示在其上方。",
    ),
    "La version {} est disponible. Ouvre le panneau pour mettre à jour.": (
        "Version {} is available. Open the panel to update.",
        "La versión {} está disponible. Abre el panel para actualizar.",
        "版本 {} 已发布。打开面板即可更新。",
    ),
    "Mise à jour installée : version {}.": (
        "Update installed: version {}.",
        "Actualización instalada: versión {}.",
        "更新已安装：版本 {}。",
    ),
    "La nouvelle version est installée mais n'a pas pu démarrer ({}). Relance FollowTheLyrics.": (
        "The new version is installed but could not start ({}). Launch FollowTheLyrics again.",
        "La nueva versión está instalada pero no pudo iniciarse ({}). Vuelve a abrir FollowTheLyrics.",
        "新版本已安装但无法启动（{}）。请重新打开 FollowTheLyrics。",
    ),
    "Version « code » : télécharge la nouvelle version sur la page ouverte.": (
        "Source version: download the new version from the page that opened.",
        "Versión de código: descarga la nueva versión en la página abierta.",
        "源码版本：请在打开的页面下载新版本。",
    ),
    "L'installation n'a pas pu se faire ({}).\n\nL'appli continue de marcher depuis ce fichier.": (
        "The installation could not be done ({}).\n\nThe app keeps running from this file.",
        "No se pudo instalar ({}).\n\nLa app sigue funcionando desde este archivo.",
        "安装未能完成（{}）。\n\n应用会继续从当前文件运行。",
    ),
    "La mise à jour a échoué ({}). Réessaie plus tard.": (
        "The update failed ({}). Try again later.",
        "La actualización falló ({}). Inténtalo más tarde.",
        "更新失败（{}）。请稍后重试。",
    ),
    "Impossible d'écrire dans le dossier du programme. Déplace {} dans un dossier à toi (Bureau, Documents…) puis réessaie.": (
        "Can't write to the program's folder. Move {} to a folder of yours (Desktop, Documents…) and try again.",
        "No se puede escribir en la carpeta del programa. Mueve {} a una carpeta tuya (Escritorio, Documentos…) y reinténtalo.",
        "无法写入程序所在文件夹。请把 {} 移到你自己的文件夹（桌面、文档等）后重试。",
    ),
    "Désinstaller FollowTheLyrics de ce PC ?": (
        "Uninstall FollowTheLyrics from this PC?",
        "¿Desinstalar FollowTheLyrics de este PC?",
        "要从此电脑卸载 FollowTheLyrics 吗？",
    ),
    "Garder tes réglages et tes zones pour une prochaine installation ?": (
        "Keep your settings and zones for a future installation?",
        "¿Conservar tus ajustes y zonas para una próxima instalación?",
        "要保留设置和区域，以便下次安装使用吗？",
    ),
    "FollowTheLyrics a été désinstallé.": (
        "FollowTheLyrics has been uninstalled.",
        "FollowTheLyrics se ha desinstalado.",
        "FollowTheLyrics 已卸载。",
    ),
    "MOT À MOT": (
        "WORD BY WORD",
        "PALABRA A PALABRA",
        "逐字",
    ),
    "LIGNE": (
        "LINE",
        "LÍNEA",
        "逐行",
    ),
    "RECHERCHE...": (
        "SEARCHING...",
        "BUSCANDO...",
        "查找中...",
    ),
    "PAS DE PAROLES": (
        "NO LYRICS",
        "SIN LETRA",
        "无歌词",
    ),
    "Bienvenue dans FollowTheLyrics": (
        "Welcome to FollowTheLyrics",
        "Bienvenido a FollowTheLyrics",
        "欢迎使用 FollowTheLyrics",
    ),
    "Les paroles de ta musique, par-dessus tes jeux.": (
        "Your music's lyrics, right over your games.",
        "La letra de tu música, sobre tus juegos.",
        "你的音乐歌词，显示在游戏之上。",
    ),
    "Lance ta musique": (
        "Play your music",
        "Pon tu música",
        "播放音乐",
    ),
    "Spotify, YouTube Music, Deezer, Apple Music… Les paroles arrivent toutes seules, sans compte à connecter.": (
        "Spotify, YouTube Music, Deezer, Apple Music… Lyrics show up on their own, with no account to connect.",
        "Spotify, YouTube Music, Deezer, Apple Music… La letra aparece sola, sin conectar ninguna cuenta.",
        "Spotify、YouTube Music、Deezer、Apple Music 等。歌词自动出现，无需登录任何账号。",
    ),
    "Joue en « fenêtré sans bordure »": (
        "Play in “borderless windowed” mode",
        "Juega en «ventana sin bordes»",
        "使用“无边框窗口”模式游戏",
    ),
    "C'est le mode d'affichage qui laisse les paroles passer par-dessus le jeu. Il se règle dans les options vidéo du jeu.": (
        "That's the display mode that lets lyrics show over the game. You set it in the game's video options.",
        "Es el modo que permite que la letra se vea sobre el juego. Se ajusta en las opciones de vídeo del juego.",
        "只有这种显示模式才能让歌词显示在游戏上方。可在游戏的视频选项中设置。",
    ),
    "Ctrl + Alt + L pour masquer": (
        "Ctrl + Alt + L to hide",
        "Ctrl + Alt + L para ocultar",
        "Ctrl + Alt + L 隐藏歌词",
    ),
    "Le raccourci marche en pleine partie. L'icône près de l'heure rouvre les réglages à tout moment.": (
        "The shortcut works mid-game. The icon near the clock reopens the settings at any time.",
        "El atajo funciona en plena partida. El icono junto al reloj reabre los ajustes en cualquier momento.",
        "游戏中也能使用该快捷键。时钟旁的图标可随时重新打开设置。",
    ),
    "Créer un raccourci sur le bureau": (
        "Create a desktop shortcut",
        "Crear un acceso directo en el escritorio",
        "创建桌面快捷方式",
    ),
    "Installer sur ce PC (icône dans le menu Démarrer)": (
        "Install on this PC (Start menu icon)",
        "Instalar en este PC (icono en el menú Inicio)",
        "安装到此电脑（开始菜单图标）",
    ),
    "C'est parti": (
        "Let's go",
        "Vamos",
        "开始使用",
    ),
    "FollowTheLyrics — zones à éviter": (
        "FollowTheLyrics — areas to avoid",
        "FollowTheLyrics — zonas a evitar",
        "FollowTheLyrics — 避让区域",
    ),
    "Clique et glisse pour dessiner une zone. Glisse une zone pour la déplacer, ses coins pour la redimensionner. Suppr l'efface.": (
        "Click and drag to draw a zone. Drag a zone to move it, its corners to resize it. Delete removes it.",
        "Haz clic y arrastra para dibujar una zona. Arrastra una zona para moverla, sus esquinas para cambiar su tamaño. Supr la borra.",
        "点击并拖动可绘制区域。拖动区域可移动，拖动角点可调整大小。按 Delete 删除。",
    ),
    "Zones d'origine": (
        "Default zones",
        "Zonas originales",
        "默认区域",
    ),
    "Tout effacer": (
        "Clear all",
        "Borrar todo",
        "全部清除",
    ),
    "Fermer": (
        "Close",
        "Cerrar",
        "关闭",
    ),
    "Enregistrer": (
        "Save",
        "Guardar",
        "保存",
    ),
    "Enregistré": (
        "Saved",
        "Guardado",
        "已保存",
    ),
    "Enregistré. Les paroles éviteront ces zones dès maintenant (Ctrl + Alt + Z en jeu pour les revoir).": (
        "Saved. Lyrics will avoid these zones from now on (Ctrl + Alt + Z in game to see them again).",
        "Guardado. La letra evitará estas zonas desde ahora (Ctrl + Alt + Z en el juego para volver a verlas).",
        "已保存。歌词从现在起会避开这些区域（游戏中按 Ctrl + Alt + Z 可再次查看）。",
    ),
    "Impossible d'enregistrer le fichier des profils.": (
        "Could not save the profiles file.",
        "No se pudo guardar el archivo de perfiles.",
        "无法保存配置文件。",
    ),
    "Les paroles s'affichent au-dessus de cette ligne": (
        "Lyrics show above this line",
        "La letra se muestra por encima de esta línea",
        "歌词显示在这条线上方",
    ),
    "Pas encore de capture de ce jeu.\nEn jeu, appuie sur Ctrl + Alt + E : elle s'affichera ici.": (
        "No capture of this game yet.\nIn game, press Ctrl + Alt + E: it will show here.",
        "Aún no hay captura de este juego.\nEn el juego, pulsa Ctrl + Alt + E: aparecerá aquí.",
        "还没有这个游戏的截图。\n在游戏中按 Ctrl + Alt + E，截图会显示在这里。",
    ),
    "Nom de la zone (minimap, chat…)": (
        "Zone name (minimap, chat…)",
        "Nombre de la zona (minimapa, chat…)",
        "区域名称（小地图、聊天等）",
    ),
    "Supprimer la zone": (
        "Delete the zone",
        "Eliminar la zona",
        "删除区域",
    ),
    "Zone {}": (
        "Zone {}",
        "Zona {}",
        "区域 {}",
    ),
    "{} (nouveau)": (
        "{} (new)",
        "{} (nuevo)",
        "{}（新）",
    ),
    "Dans LoL : Echap > Video > Mode fenetre > « Sans bordure ».": (
        "In LoL: Esc > Video > Window mode > “Borderless”.",
        "En LoL: Esc > Vídeo > Modo de ventana > «Sin bordes».",
        "在 LoL 中：Esc > 视频 > 窗口模式 > “无边框”。",
    ),
    "Dans Cyberpunk : Parametres > Graphismes (ou Video) > Mode fenetre > « Fenetre sans bordure ».": (
        "In Cyberpunk: Settings > Graphics (or Video) > Window mode > “Windowed borderless”.",
        "En Cyberpunk: Ajustes > Gráficos (o Vídeo) > Modo de ventana > «Ventana sin bordes».",
        "在 Cyberpunk 中：设置 > 图形（或视频）> 窗口模式 > “无边框窗口”。",
    ),
    "Dans WoW : Echap > Options > Graphismes > Mode d'affichage > « Fenetre (plein ecran) ».": (
        "In WoW: Esc > Options > Graphics > Display mode > “Windowed (Fullscreen)”.",
        "En WoW: Esc > Opciones > Gráficos > Modo de pantalla > «Ventana (pantalla completa)».",
        "在 WoW 中：Esc > 选项 > 图形 > 显示模式 > “窗口（全屏）”。",
    ),
    "Dans Valorant : Parametres > Video > Mode d'affichage > « Fenetre plein ecran ».": (
        "In Valorant: Settings > Video > Display mode > “Windowed Fullscreen”.",
        "En Valorant: Ajustes > Vídeo > Modo de pantalla > «Ventana a pantalla completa».",
        "在 Valorant 中：设置 > 视频 > 显示模式 > “窗口全屏”。",
    ),
    "Dans Fortnite : Parametres > Video > Mode fenetre > « Plein ecran fenetre ».": (
        "In Fortnite: Settings > Video > Window mode > “Windowed Fullscreen”.",
        "En Fortnite: Ajustes > Vídeo > Modo de ventana > «Pantalla completa en ventana».",
        "在 Fortnite 中：设置 > 视频 > 窗口模式 > “窗口化全屏”。",
    ),
    "Dans Minecraft : Options > Graphismes > Plein ecran : NON, puis agrandis la fenetre.": (
        "In Minecraft: Options > Video Settings > Fullscreen: OFF, then maximise the window.",
        "En Minecraft: Opciones > Gráficos > Pantalla completa: NO, y maximiza la ventana.",
        "在 Minecraft 中：选项 > 视频设置 > 全屏：关，然后最大化窗口。",
    ),
    "Dans GTA V : Parametres > Graphismes > Type d'ecran > « Fenetre sans bordure ».": (
        "In GTA V: Settings > Graphics > Screen type > “Windowed Borderless”.",
        "En GTA V: Ajustes > Gráficos > Tipo de pantalla > «Ventana sin bordes».",
        "在 GTA V 中：设置 > 图形 > 屏幕类型 > “无边框窗口”。",
    ),
    "LIGNE · RECHERCHE DU MOT À MOT...": (
        "LINE · LOOKING FOR WORD BY WORD...",
        "LÍNEA · BUSCANDO PALABRA A PALABRA...",
        "逐行 · 正在查找逐字歌词...",
    ),
}
