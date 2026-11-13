from followthelyrics import desktop


def main():
    system = desktop.current()
    media = system.media
    if media is None:
        print(f"Morceau en cours indisponible sur {system.name}.")
        return
    session = media.open()
    try:
        now_playing = session.now_playing((), None)
        print(now_playing if now_playing else "Rien ne joue.")
        image = session.cover((), None)
    finally:
        session.close()
    if image:
        print(f"pochette : {len(image)} octets, debut {image[:4]!r}")
    else:
        print("pas de pochette")


if __name__ == "__main__":
    main()
