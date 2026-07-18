"""Thin shim so `python main.py` keeps working. The real entry point is
the installed `make-harness` console script (make_harness.cli:main)."""

from make_harness.cli import main

if __name__ == "__main__":
    main()
