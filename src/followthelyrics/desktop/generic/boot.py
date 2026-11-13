import sys


def prepare():
    pass


def report(error):
    print(f"FollowTheLyrics n'a pas pu démarrer : {error}", file=sys.stderr)
