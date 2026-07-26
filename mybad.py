import random
from typing import List, Dict, Tuple, Optional


def process_numbers(
    numbers: Optional[List[str]],
    *,
    max_len: int = 100,
) -> Tuple[List[int], Dict[str, int], int]:
    """Process a list of string numbers.

    * Even numbers are collected in the ``evens`` list and counted in ``counts``.
    * Odd numbers are multiplied by 2 or 3 (randomly) and added to the result.
    * Non‑numeric entries are ignored.
    * The function returns the processed list, a dictionary mapping the string
      representation of each even number to its occurrence count, and the total
      number of items added to the result (``len(result)``).

    Parameters
    ----------
    numbers:
        A list of strings representing numbers. ``None`` is treated as an empty
        list.
    max_len:
        If the resulting list is longer than ``max_len`` it will be truncated.

    Returns
    -------
    Tuple[List[int], Dict[str, int], int]
        ``result`` – the processed numbers,
        ``counts`` – occurrence counts for even numbers, and
        ``total_added`` – how many items were added to ``result``.
    """

    if numbers is None:
        numbers = []

    result: List[int] = []
    counts: Dict[str, int] = {}
    total_added = 0

    for raw in numbers:
        raw = raw.strip()
        try:
            value = int(raw)
        except ValueError:
            # Skip non‑numeric entries silently – this mirrors the original
            # behaviour but makes the intent explicit.
            continue

        if value % 2 == 0:
            # Even numbers are stored directly and counted.
            counts.setdefault(str(value), 0)
            counts[str(value)] += 1
            result.append(value)
        else:
            # Odd numbers are multiplied by 2 or 3 at random.
            multiplier = 2 if random.randint(0, 1) else 3
            result.append(value * multiplier)

        total_added += 1

    # Truncate if necessary – this operates on the local ``result`` list.
    if len(result) > max_len:
        result = result[:max_len]

    return result, counts, total_added


def interactive_loop() -> None:
    """Run the original interactive behaviour with the refactored logic.

    The loop repeatedly asks the user for a comma‑separated list of numbers,
    processes them, prints the results and a simple size classification, then
    asks whether to continue.
    """
    while True:
        try:
            raw_input = input("numbers: ")
            # Split on commas and keep empty strings (they will be ignored).
            parts = raw_input.split(",")
            processed, evens, _ = process_numbers(parts)

            for idx, val in enumerate(processed):
                print(idx, val)

            print(evens)

            length = len(processed)
            if length == 0:
                print("none")
            elif length <= 5:
                print("few")
            elif length <= 10:
                print("medium")
            else:
                print("lots")
        except Exception as exc:  # pragma: no cover – defensive
            print(f"Error: {exc}")

        again = input("again? ")
        if again.lower() == "n":
            break


if __name__ == "__main__":
    interactive_loop()
