"""Adapters. Provider names live here and nowhere else.

``fake`` ships with the core and needs nothing. Every other module is a pip extra and
imports its dependency lazily, so ``import praxis_core.providers`` never pulls a vendor SDK.
"""
