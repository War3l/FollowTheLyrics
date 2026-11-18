# Privacy

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
