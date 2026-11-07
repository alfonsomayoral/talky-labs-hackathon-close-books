import os

# Set before anything imports Polars: without it, its allocator keeps 1 GB of freed memory after loading a phase.
os.environ.setdefault("_RJEM_MALLOC_CONF", "dirty_decay_ms:0,muzzy_decay_ms:0")
