"""Natural-language question -> validated structured query -> parameterized SQL.

Pipeline (owcsmuse.nlq.pipeline.ask):
  1. parse     question -> StructuredQuery (rule-based by default; optional Claude parser)
  2. resolve   entity names -> ids through owcsmuse.resolve; ambiguity -> candidates
  3. validate  every metric / column / filter value against the live schema
  4. compile   StructuredQuery -> (sql, params) over the agg_* layer; no model ever writes SQL
  5. execute   and attach stat coverage to the answer

Every step can end in an Unanswerable with a specific reason code.
"""

from .schema import Filters, StructuredQuery, Unanswerable

__all__ = ["Filters", "StructuredQuery", "Unanswerable"]
