"""Generate fine-tuning data in the Pick-and-Place block DSL format.

This package transcribes every task in ``Tasks.md`` into an executable program,
runs it step-by-step against the real (headless) simulator, and emits one
``{input, output, metadata}`` dataset entry per LLM invocation, exactly as the
context-manager loop in ``DSL.md`` prescribes.
"""
