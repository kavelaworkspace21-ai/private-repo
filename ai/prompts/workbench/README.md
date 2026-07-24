# Workbench prompt contracts (Gate G8 — human review required)

The generation prompt for every Workbench workflow is assembled in
`app/services/workbench/engine.py::_llm_generate` from:
1. the AI Answer Safety Contract (no source → no answer; no prediction; [●] for unknown facts),
2. the workflow's exact section schema from `app/services/workbench/workflows.py` (pack §5),
3. the retrieved verbatim statute grounding (the only citable law).

These schemas and rules ARE the prompts-as-data. A senior advocate must review each
workflow's schema + sample outputs before beta use (pack §7). Do not self-certify.
