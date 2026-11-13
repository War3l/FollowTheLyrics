import argparse

from followthelyrics.lyrics import providers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("artist", nargs="?", default="")
    parser.add_argument("duration", nargs="?", type=float, default=0.0)
    args = parser.parse_args()
    lines = providers.fetch_lyrics(
        args.title, args.artist, duration=args.duration
    )
    if not lines:
        print("Pas de paroles synchronisees")
        return
    kind = "MOT A MOT" if any(line.chars for line in lines) else "par ligne"
    print(f"{len(lines)} lignes, timing {kind}")


if __name__ == "__main__":
    main()
