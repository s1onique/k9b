"""Scripts/ci package.

This __init__.py makes scripts/ci a proper Python package, enabling
test imports of the promotion runtime gate modules without sys.path
manipulation in conftest.py.
"""
