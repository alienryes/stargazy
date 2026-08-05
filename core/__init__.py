"""Shared engine for the stargazing display builds.

Nothing in here knows the size or layout of a panel. Each build supplies its own
geometry and drawing, and imports the data sources, imagery, sky animation and
framebuffer handling from these modules.
"""
