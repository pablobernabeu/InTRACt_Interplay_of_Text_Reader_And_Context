"""Pipeline stages, one module each.

A stage module defines STAGE (a cli.Stage) and run(ctx) -> dict of counts. The
command line discovers every module in this package, so adding a stage never
touches a shared registry.
"""
