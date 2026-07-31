"""Diversify the separators used in ``locations.json``.

Every location currently glues its words together with underscores, which
makes the dataset monotonous. This script rewrites the list so each
underscore is independently replaced by a randomly chosen separator pattern,
drawn from 10 *new* patterns plus the original underscore (still a valid
pattern, of course):

    1.  " "     whitespace
    2.  ""      "next letter capital, nothing else" (camelCase join)
    3.  "/"     forward slash
    4.  "\\"     backslash
    5.  "-"     hyphen / dash
    6.  "."     dot
    7.  "::"    double colon
    8.  "|"     pipe
    9.  ""      concatenation (nothing at all, no capitalisation)
    10. "+"     plus
    (+) "_"     the underscore itself

On top of the separator shuffle, two capitalisation rules are applied:

    * exactly ~10% of all words get their first letter capitalised, and
    * exactly ~10% of the locations are fully upper-cased.

The file is rewritten **in place**. Pass ``--seed`` for reproducible output;
note that re-running compounds the transformation (a run finds fewer
underscores than the last), so keep a copy of the original if you need to
regenerate from scratch.
"""

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCATIONS_PATH = HERE / "locations.json"

# Sentinel marking the "next letter capital, nothing else" pattern: the
# underscore vanishes and the following word's first letter is capitalised.
CAMEL = "\0camel\0"

# The 10 new separator patterns plus the underscore itself.
SEPARATORS: list[str] = [
    "_",    # underscore (original, still available)
    " ",    # whitespace
    CAMEL,  # next letter capital, nothing else
    "/",    # forward slash
    "\\",   # backslash
    "-",    # hyphen / dash
    ".",    # dot
    "::",   # double colon
    "|",    # pipe
    "",     # concatenation (nothing at all)
    "+",    # plus
]

WORD_CAP_FRACTION = 0.10   # ~10% of words get their first letter capitalised
FULL_CAP_FRACTION = 0.10   # ~10% of locations become fully upper-cased


def cap_first(word: str) -> str:
    """Capitalise only the first character, leaving the rest untouched."""
    return word[:1].upper() + word[1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible output")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    with LOCATIONS_PATH.open(encoding="utf-8") as f:
        locations: list[str] = json.load(f)

    word_lists = [loc.split("_") for loc in locations]

    # Pick exactly ~10% of all words (across every location) to capitalise.
    word_positions = [(i, j) for i, words in enumerate(word_lists) for j in range(len(words))]
    n_word_caps = round(len(word_positions) * WORD_CAP_FRACTION)
    cap_words = set(rng.sample(word_positions, n_word_caps))

    # Pick exactly ~10% of the locations to fully upper-case.
    n_full_caps = round(len(locations) * FULL_CAP_FRACTION)
    full_caps = set(rng.sample(range(len(locations)), n_full_caps))

    transformed: list[str] = []
    for i, words in enumerate(word_lists):
        words = [cap_first(w) if (i, j) in cap_words else w for j, w in enumerate(words)]

        result = words[0]
        for word in words[1:]:  # one iteration per underscore
            sep = rng.choice(SEPARATORS)
            if sep == CAMEL:
                result += cap_first(word)
            else:
                result += sep + word

        if i in full_caps:
            result = result.upper()
        transformed.append(result)

    with LOCATIONS_PATH.open("w", encoding="utf-8") as f:
        json.dump(transformed, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Locations rewritten:   {len(transformed)} -> {LOCATIONS_PATH.name}")
    print(f"Words capitalised:     {n_word_caps} / {len(word_positions)}")
    print(f"Locations upper-cased: {n_full_caps} / {len(locations)}")


if __name__ == "__main__":
    main()
