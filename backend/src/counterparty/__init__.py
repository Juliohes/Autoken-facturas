"""Verificación del CIF de la contraparte (S2.8, ADR-0011).

Módulo de dominio que responde "¿este CIF existe y su razón social es la que dice la factura?".
Orquesta cuatro niveles de barato/rápido a caro/autoritativo: L1 estructura (`shared.tax_id`), L2
supplier master del tenant (`counterparties`, RLS por tenant), L3 resolución externa (AEAT censal /
VIES / BORME, tras la interfaz `CifResolver`) y L4 caché global de resoluciones (`cif_lookups`).

Regla de oro de disponibilidad: la caída/timeout de un tercero produce `unverified` (revisar
manual), nunca `invalid`/`not_found`; una factura jamás se bloquea por la caída de un tercero.
"""
