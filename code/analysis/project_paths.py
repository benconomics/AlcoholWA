"""Locate inputs and exhibits for both checkouts of this project.

The Dropbox tree keeps these scripts at ``<data root>/2026/code/analysis`` and
writes exhibits to ``<data root>/breath_panel_2026_update``. The GitHub checkout
keeps the scripts at ``<repo>/code/analysis`` and the published exhibits at
``<repo>/results/breath_panel_2026_update``.
"""

from __future__ import annotations

from pathlib import Path


def analysis_dir() -> Path:
    return Path(__file__).resolve().parent


def _dropbox_layout() -> bool:
    here = analysis_dir()
    return here.parent.name == "code" and here.parent.parent.name == "2026"


def data_root() -> Path:
    """Directory that holds private extracts and, in the Dropbox tree, exhibits."""
    here = analysis_dir()
    if _dropbox_layout():
        return here.parents[2]
    return here.parents[1]


def breath_update_dir() -> Path:
    """Directory of the 2026 breath-test tables, figures, and briefs."""
    root = data_root()
    if _dropbox_layout():
        return root / "breath_panel_2026_update"
    return root / "results" / "breath_panel_2026_update"
