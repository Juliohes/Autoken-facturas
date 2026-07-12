"""Resolvers externos del CIF de contraparte (L3): interfaz común + adaptadores reales.

`base` define el contrato (`CifResolver`, `ResolutionResult`, `ResolverUnavailable`). Los concretos
(`aeat`, `vies`, `borme`) hablan con cada fuente tras esa interfaz; el servicio no los conoce, solo
la interfaz. En CI se doblan (sin red); la llamada real se ejerce en staging.
"""
