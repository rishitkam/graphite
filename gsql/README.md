- `01_schema.gsql`: vertex and edge definitions. Written against the real
  dataset README and validated column headers, not guessed. Not yet run
  against a live instance, so treat it as a first draft until it's actually
  loaded once and any syntax errors are fixed.

Loading jobs come next, once there's a TigerGraph instance to iterate
against. Writing those blind, with no GSQL console to check them against,
is a worse use of time than writing them against real error messages.
