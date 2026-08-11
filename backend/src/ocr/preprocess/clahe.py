"""Preprocesado CLAHE (contraste local adaptativo) de una factura -- 3ª variante de imagen del
benchmark (S6.7, spec docs/specs/S6.7-benchmark-real-motor-variante.md §5.1).

Módulo PURO (sin red, sin I/O de infraestructura), mismo espíritu que `ocr.preprocess.enhance`
(S2.9): solo transforma bytes de imagen, nunca se persiste en MinIO ni se enseña al usuario --
insumo efímero del benchmark. Función SÍNCRONA con coste real de CPU (decodificar + CLAHE +
codificar PNG): el llamador es responsable de invocarla con `asyncio.to_thread`, igual que
`enhance_invoice_image`, para no bloquear el event loop del worker.

A diferencia de un contraste global fijo (`enhance.py`), CLAHE reparte el realce por regiones de la
imagen -- penaliza mucho menos las sombras, decisivo en fotos de móvil con luz desigual. Pillow no
ofrece CLAHE nativo; se usa `cv2.createCLAHE` (`opencv-python-headless`, nueva dependencia de esta
tarea -- ver `pyproject.toml`), aplicado solo al canal de luminancia (espacio LAB: L = luminancia,
A/B = color) para no
distorsionar el color -- práctica estándar de CLAHE sobre imágenes en color. Se genera SIEMPRE a
partir del fichero original, nunca de una versión ya reducida (mismo motivo que `enhance.py`:
reducir antes de aplicar CLAHE pierde el detalle que el propio CLAHE necesita).

Parámetros conservadores, sin afinar contra el bench real (mismo criterio que `enhance.py`, spec
§6): `clipLimit`/`tileGridSize` son el único punto de ajuste cuando Julio decida invertir ese
presupuesto.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image

from ocr.preprocess._guards import open_bounded_image

__all__ = ["CLAHE_CONTENT_TYPE", "clahe_invoice_image"]

# El benchmark siempre produce PNG, cualquiera que sea el formato de entrada -- mismo criterio que
# `ENHANCED_CONTENT_TYPE` de `enhance.py`.
CLAHE_CONTENT_TYPE = "image/png"

# Límite de contraste conservador (valores altos amplifican ruido en zonas casi uniformes) y una
# rejilla de 8x8 (tamaño de mosaico estándar para CLAHE, ni tan fino que amplifique ruido de sensor
# ni tan grueso que se aproxime a un contraste global).
_CLIP_LIMIT = 2.0
_TILE_GRID_SIZE = (8, 8)


def clahe_invoice_image(content: bytes, content_type: str) -> bytes:
    """Aplica CLAHE sobre el canal de luminancia; devuelve siempre `CLAHE_CONTENT_TYPE`.

    Lanza `UnsupportedImageError`/`ImageTooLargeError` vía `ocr.preprocess._guards.
    open_bounded_image` (mismas guardas que `enhance_invoice_image`, sin duplicarlas -- ver ahí el
    detalle). Síncrona y con coste real de CPU: ver nota del módulo sobre `to_thread`.
    """
    image = open_bounded_image(content, content_type).convert("RGB")

    rgb_array = np.array(image)
    lab_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2LAB)
    luminance, channel_a, channel_b = cv2.split(lab_array)

    clahe = cv2.createCLAHE(clipLimit=_CLIP_LIMIT, tileGridSize=_TILE_GRID_SIZE)
    equalized_luminance = clahe.apply(luminance)

    equalized_lab = cv2.merge((equalized_luminance, channel_a, channel_b))
    equalized_rgb = cv2.cvtColor(equalized_lab, cv2.COLOR_LAB2RGB)

    result_image = Image.fromarray(equalized_rgb, mode="RGB")
    buffer = io.BytesIO()
    result_image.save(buffer, format="PNG")
    return buffer.getvalue()
