"""FalkorDB connection: one client per process, graph name from settings."""

from functools import lru_cache

from falkordb import FalkorDB, Graph

from pagersage.config import get_settings


@lru_cache(maxsize=1)
def get_db() -> FalkorDB:
    s = get_settings()
    return FalkorDB(
        host=s.falkordb_host,
        port=s.falkordb_port,
        username=s.falkordb_username,
        password=s.falkordb_password,
        socket_connect_timeout=3,
        socket_timeout=10,
    )


def get_graph(name: str | None = None) -> Graph:
    """The PagerSage graph, or another named graph (tests use throwaway names)."""
    return get_db().select_graph(name or get_settings().pagersage_graph)


def ping() -> bool:
    """True when FalkorDB answers. Raises redis errors / OSError when it does not."""
    return bool(get_db().connection.ping())
