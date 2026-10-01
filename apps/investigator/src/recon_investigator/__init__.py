"""Investigation worker: a separate process with its own permissions (ADR-002).

It runs the bounded agent and launches fintech-mcp-server per investigation; the
reconciliation worker never imports model code.
"""
