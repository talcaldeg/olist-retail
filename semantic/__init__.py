"""Semantic layer: four metrics over the marts, compiled to SQL without an LLM."""

from semantic.compiler import (
    SemanticError,
    compile_query,
    consultar_metrica,
    listar_metricas,
)

__all__ = ["SemanticError", "compile_query", "consultar_metrica", "listar_metricas"]
