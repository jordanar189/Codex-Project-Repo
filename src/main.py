"""Terminal mini-golf party game: golf with your friends."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import List


PAR_VALUES = [3, 4, 5, 3, 4, 5, 3, 4, 5]


@dataclass
class Player:
    """Represents one golfer and their score card."""

    name: str
    strokes_per_hole: List[int]

    def total_strokes(self) -> int:
        """Return total strokes across all completed holes."""
        return sum(self.strokes_per_hole)

    def score_to_par(self) -> int:
        """Return score relative to par for completed holes."""
        played_holes = len(self.strokes_per_hole)
        return self.total_strokes() - sum(PAR_VALUES[:played_holes])


@dataclass
class Hole:
    """Represents one mini-golf hole."""

    number: int
    par: int
    distance: int
    hazard_chance: float


def create_course(seed: int | None = None) -> List[Hole]:
    """Generate a deterministic 9-hole course when seed is set."""
    if seed is not None:
        random.seed(seed)

    holes: List[Hole] = []
    for index, par in enumerate(PAR_VALUES, start=1):
        distance = random.randint(30, 90)
        hazard_chance = round(random.uniform(0.12, 0.30), 2)
        holes.append(Hole(index, par, distance, hazard_chance))
    return holes


def calculate_shot_result(power: int, hole: Hole) -> tuple[int, str]:
    """Return yards moved and event text for a single shot."""
    base_distance = power + random.randint(-8, 8)

    if random.random() < hole.hazard_chance:
        setback = random.randint(8, 22)
        return max(0, base_distance - setback), "Hazard hit! Ball slowed down."

    bonus = 0
    if 45 <= power <= 65 and random.random() < 0.25:
        bonus = random.randint(5, 15)
    return max(0, base_distance + bonus), "Clean shot."


def play_hole(player: Player, hole: Hole) -> int:
    """Play one hole for a player and return stroke count."""
    print(f"\n--- Hole {hole.number} | Par {hole.par} | {hole.distance} yards ---")
    distance_left = hole.distance
    strokes = 0

    while distance_left > 0:
        strokes += 1
        print(f"{player.name}, shot {strokes}. Distance left: {distance_left} yards")
        power = prompt_for_power()
        movement, event = calculate_shot_result(power, hole)

        if movement >= distance_left:
            print(f"{event} You sink it! 🎉")
            distance_left = 0
        else:
            distance_left -= movement
            print(f"{event} Ball moved {movement} yards.")

    print(f"{player.name} finished in {strokes} stroke(s).")
    return strokes


def prompt_for_power() -> int:
    """Read a valid shot power value from stdin."""
    while True:
        raw = input("Choose shot power (20-90): ").strip()
        if not raw.isdigit():
            print("Please enter a whole number.")
            continue

        power = int(raw)
        if 20 <= power <= 90:
            return power

        print("Power must be between 20 and 90.")


def print_leaderboard(players: List[Player]) -> None:
    """Print leaderboard sorted by score to par then total strokes."""
    ranked = sorted(players, key=lambda p: (p.score_to_par(), p.total_strokes(), p.name.lower()))

    print("\n=== Leaderboard ===")
    for position, player in enumerate(ranked, start=1):
        relative = player.score_to_par()
        sign = "+" if relative > 0 else ""
        print(
            f"{position}. {player.name:<14} "
            f"Strokes: {player.total_strokes():<3} "
            f"To Par: {sign}{relative}"
        )


def prompt_for_players() -> List[Player]:
    """Collect player names and initialize score cards."""
    while True:
        raw = input("How many friends are playing? (1-6): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= 6:
            total_players = int(raw)
            break
        print("Enter a number from 1 to 6.")

    players: List[Player] = []
    for number in range(1, total_players + 1):
        while True:
            name = input(f"Name for Player {number}: ").strip()
            if name:
                players.append(Player(name=name, strokes_per_hole=[]))
                break
            print("Name cannot be empty.")

    return players


def main() -> None:
    """Run the game loop for a full round of mini golf."""
    print("🏌️ Welcome to Golf With Your Friends (Terminal Edition)!")
    print("Play 9 holes, avoid hazards, and chase the best score versus par.")

    players = prompt_for_players()
    holes = create_course()

    for hole in holes:
        for player in players:
            strokes = play_hole(player, hole)
            player.strokes_per_hole.append(strokes)

        print_leaderboard(players)

    print("\nRound complete! Final results:")
    print_leaderboard(players)


if __name__ == "__main__":
    main()
