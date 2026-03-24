"""Simple Hello World entry point."""

import random

# some comment
# some comment

# some comment
# some comment

# some comment
# some comment

# some comment
# some comment

# some comment
# some comment

_PLANETS = (
    "Mercury",
    "Venus",
    "Earth",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
)


def hello_welcome_planet() -> None:
    planet = random.choice(_PLANETS)
    print(f"hello welcome to {planet}")


def hello_universe() -> None:
    print("Hello, universe!")


if __name__ == "__main__":
    print("Hello, world!")
    hello_universe()
