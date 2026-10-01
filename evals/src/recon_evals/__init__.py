"""Evaluation framework (M7): one runner, versioned manifests, labelled reports.

Labels follow docs/07-evals.md: MEASURED (a real component ran), SIMULATED (scripted
model output) and SKIPPED (a dependency was not available). EXPECTED targets live only
in manifests as gates; they are never reported as results.
"""
