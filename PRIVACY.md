# Confidentialité / Privacy

[Français](#français) · [English](#english)

## Français

FollowTheLyrics ne demande aucun compte, ne contient ni publicité ni outil de mesure d'audience,
et n'envoie rien à son auteur. Pour trouver les paroles, il contacte toutefois des services en
ligne. Voici exactement ce qui sort de ton ordinateur.

| Quand | Ce qui est envoyé | À qui | Peut-on le couper ? |
|---|---|---|---|
| Un morceau démarre | Son titre, son artiste, son album et sa durée | NetEase Cloud Music (`music.163.com`) et LRCLIB (`lrclib.net`) | Non, c'est le cœur de l'appli. Quitter l'appli arrête tout envoi |
| Le mot à mot manque | Le titre, l'artiste et la durée | LiriQo (`api.liriqo-alfarrizi.my.id`) | Oui : page **Musique** |
| La traduction est activée | Le texte des paroles affichées | Google Traduction (`translate.googleapis.com`) | Oui : page **Musique** |
| De temps en temps | Une simple demande « quelle est la dernière version ? » | GitHub (`api.github.com`) | Non |
| Tu cliques sur **Mettre à jour** | Le téléchargement du nouveau programme | GitHub | Oui : ne pas cliquer |

Comme pour toute connexion Internet, ces services voient ton adresse IP. Aucun identifiant, nom
ou adresse e-mail n'est transmis.

Ce qui reste sur ton ordinateur :

- **Le son** : l'appli écoute la sortie audio du PC pour suivre le rythme. Rien n'est enregistré
  ni envoyé.
- **Le programme au premier plan** : l'appli regarde quel jeu est ouvert pour placer les paroles.
  Cette information ne quitte pas l'ordinateur.
- **Les réglages, les profils de jeu et les paroles déjà trouvées** : ils sont rangés dans
  `%APPDATA%\FollowTheLyrics` (Windows) ou `~/.config/FollowTheLyrics` (Linux).

Les paroles sont gardées sur ton ordinateur pour ne pas être redemandées à chaque écoute.

Une question ? Ouvre un ticket sur
[GitHub](https://github.com/War3l/FollowTheLyrics/issues).

## English

FollowTheLyrics needs no account, contains no ads and no analytics, and sends nothing to its
author. To find lyrics, it does contact online services. Here is exactly what leaves your
computer.

| When | What is sent | To whom | Can it be turned off? |
|---|---|---|---|
| A track starts | Its title, artist, album and duration | NetEase Cloud Music (`music.163.com`) and LRCLIB (`lrclib.net`) | No, this is the core of the app. Quitting the app stops all requests |
| Word timing is missing | The title, artist and duration | LiriQo (`api.liriqo-alfarrizi.my.id`) | Yes: **Music** page |
| Translation is on | The text of the lyrics shown | Google Translate (`translate.googleapis.com`) | Yes: **Music** page |
| From time to time | A plain "what is the latest version?" request | GitHub (`api.github.com`) | No |
| You click **Update** | The download of the new program | GitHub | Yes: do not click |

As with any Internet connection, these services see your IP address. No identifier, name or
e-mail address is transmitted.

What stays on your computer:

- **Sound**: the app listens to the PC's audio output to follow the beat. Nothing is recorded or
  sent.
- **The foreground program**: the app checks which game is open to place the lyrics. This never
  leaves the computer.
- **Settings, game profiles and lyrics already found**: stored in `%APPDATA%\FollowTheLyrics`
  (Windows) or `~/.config/FollowTheLyrics` (Linux).

Lyrics are kept on your computer so they are not requested again on each listen.

A question? Open an issue on [GitHub](https://github.com/War3l/FollowTheLyrics/issues).
