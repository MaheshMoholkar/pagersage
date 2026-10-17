"""HTTP routes, one module per area. Routes stay thin: they validate input with pydantic and
call the tool / system functions in contracts/tools.py, which own every graph query."""
