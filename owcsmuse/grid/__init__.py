"""OWCS Grid: a daily 3x3 trivia game beside Muse (docs/grid/BETA.md).

`store` reads the published puzzles from scope/ and needs nothing beyond the standard library; `router` is the
FastAPI layer over it. Import the one you need: this package imports neither, so the store works without the api extra.
"""
