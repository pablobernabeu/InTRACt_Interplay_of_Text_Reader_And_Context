"""The InTRACt feature pipeline.

Computes the registered text features of the Let's Story catalogue, one stage at a
time, so that each stage can run as its own job on ARC. Before in-principle
acceptance it runs only on public data; see lock.py.
"""

__version__ = "0.1.0.dev0"
