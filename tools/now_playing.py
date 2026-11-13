import asyncio

from followthelyrics.playback import media


def main():
    now_playing = asyncio.run(media.get_now_playing())
    print(now_playing if now_playing else "Rien ne joue.")
    image = asyncio.run(media.get_thumbnail())
    if image:
        print(f"pochette : {len(image)} octets, debut {image[:4]!r}")
    else:
        print("pas de pochette")


if __name__ == "__main__":
    main()
