# Dataset de evaluación OCR (ground truth) — tarea 1.1

Conjunto de facturas reales **anotadas a mano** con sus valores correctos. Es la vara de medir
del bench de motores OCR (tarea 1.2): cada motor se puntúa comparando su lectura contra el
ground truth de este directorio. La calidad de estas anotaciones es crítica — **un valor mal
anotado invierte la señal del bench** (penaliza al motor que acertó y premia al que falló), así
que ante la duda se deja `null` y se marca para revisión, nunca se inventa.

> Datos sensibles: las imágenes/PDF de las facturas reales **no se versionan** (ver `.gitignore`:
> `docs/ocr-eval/**/*.{pdf,png,jpg,jpeg}` está excluido). Solo se versionan los `*.gt.json`.
> Los binarios originales viven en `img/` (ignorado) y, fuera del repo, en `entregas/facturas/`.

## Estructura

```
docs/ocr-eval/
├── README.md            # este documento
├── img/                 # binarios de las facturas (gitignored, NO se suben)
│   ├── gt-0001.pdf
│   └── ...
├── gt-0001.gt.json      # ground truth versionado (uno por factura)
└── ...
```

El bench se carga con `ocr.bench.dataset.load_dataset(Path("docs/ocr-eval"))`, que lee todos los
`*.gt.json`, valida su formato y resuelve `imagen` relativo a este directorio.

## Formato de `<id>.gt.json`

```json
{
  "id": "gt-0001",
  "imagen": "img/gt-0001.pdf",
  "origen": "factura-2.pdf",
  "estado": "verificado",
  "dificultad": "facil",
  "notas": "PDF digital nativo; exento de IVA.",
  "campos_pendientes": [],
  "campos": {
    "numero": "04/2026",
    "fecha": "2026-05-18",
    "emisor_nombre": "LUMAPA2 BROKERS SL",
    "emisor_nif": "B56922321",
    "receptor_nombre": "HISPALAR NEW CENTURY S.A.",
    "receptor_nif": "A87563888",
    "tramos": [{"base": "996.40", "iva_pct": "0", "cuota": "0.00"}],
    "irpf_cuota": null,
    "total": "996.40"
  }
}
```

`dataset.py` solo lee `id`, `imagen`, `dificultad`, `notas` y `campos`. Los campos extra
(`origen`, `estado`, `campos_pendientes`) son metadatos de anotación y se ignoran al cargar,
pero sirven para el flujo de revisión y para filtrar el subconjunto verificado.

### Reglas de anotación (innegociables)

1. **Punto decimal, sin separador de miles.** `"1234.56"`, nunca `"1.234,56"` ni `"1234,56"`.
   El parser usa `Decimal(str(valor))` y la coma reventaría. Importes con 2 decimales.
2. **Fecha en ISO 8601** `AAAA-MM-DD` (la factura suele mostrar `DD/MM/AAAA`).
3. **NIF/CIF/NIE** en mayúsculas y sin espacios (`"B56922321"`). Si es un identificador
   extranjero (p.ej. EIN de EE.UU.) se anota tal cual y se indica en `notas`.
4. **Campo no presente o ilegible = `null`** (regla anti-alucinación, §1 del plan). Nunca se
   adivina. Un `null` en el ground truth = ese campo no se puntúa para esa factura (no cuenta
   como fallo del motor). Distinto de un valor real que el motor no leyó (eso sí es fallo).
5. **`tramos`** = lista de tramos de IVA, cada uno `{base, iva_pct, cuota}` (todo string con
   punto). `iva_pct` es el tipo (`"21"`, `"10"`, `"4"`, `"0"`). Factura exenta → un tramo con
   `iva_pct "0"` y `cuota "0.00"`. Multi-tramo → un objeto por tipo. Se compara como
   multiconjunto (el orden no importa).
6. **`irpf_cuota`** = importe (€) de la retención de IRPF, no el porcentaje. Sin retención /
   "no sujeto" → `null`.
7. **`numero`** = número de factura tal cual aparece impreso (se conserva el formato, p.ej.
   `"04/2026"`, `"I260943"`, `"FRA-2026-001"`).

### Flujo de verificación (patrón oro = factura original de Julio)

Cada `.gt.json` lleva `estado`:

- **`verificado`** — valores confirmados contra la fuente fiable (PDF digital nativo, o el dato
  original en el sistema Setex v1). Entra en el bench con plena confianza.
- **`borrador`** — lectura de mejor esfuerzo sobre una foto de móvil (baja resolución / borrosa
  / rotada). Los campos no confirmados se listan en `campos_pendientes` y **deben ser validados
  por Julio contra la factura original** antes de pasar a `verificado`. Mientras siga en
  `borrador`, el bench debería ejecutarse sobre el subconjunto verificado o tratar estos casos
  como provisionales.

Para revisar un borrador cómodamente hay recortes ampliados (cabecera/cuerpo/pie, con las dos
rotaciones para las fotos apaisadas) generados a partir del original; ver `notas` de cada caso.

## Inventario

| id | origen | tipo | estado |
|----|--------|------|--------|
| gt-0001 | factura-2.pdf (LUMAPA2 BROKERS SL) | PDF digital | verificado |
| gt-0002 | Factura pago VFR Lite (Boutique Holdings LLC) | PDF digital | verificado |
| gt-0003..gt-0006 | Capturas (facturas Coca-Cola, foto sobre mesa) | foto | borrador |
| gt-0007..gt-0020 | Fotos WhatsApp (varios proveedores) | foto | borrador |

El detalle origen→id completo está en `notas`/`origen` de cada fichero.
