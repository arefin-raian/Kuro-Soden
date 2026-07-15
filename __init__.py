"""Kage (影 — Shadow) — Multi-Bot Pipeline for NekoFetch.

Four specialized anime-inspired bots working as a pipeline:

    Lelouch  (Code Geass)      — Request intake, dedup, admin assignment
    Levi     (Attack on Titan)  — Source selection, download, processing
    Senku    (Dr. Stone)        — Channel creation, content generation
    Gojo     (Jujutsu Kaisen)   — Publishing, index, channel recovery

All bots share NekoFetch's infrastructure (PostgreSQL, MongoDB, Redis)
and communicate through shared database state transitions.
"""

__version__ = "0.1.0"
