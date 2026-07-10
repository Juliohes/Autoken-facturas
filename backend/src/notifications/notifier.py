"""Seam de notificaciones: interfaz `Notifier` + backend en memoria para test/dev (S1.4).

El dominio (registro, S1.4) avisa al `tenant_admin` a través de esta interfaz **sin conocer el
transporte**. En test/dev, sin SMTP configurado, se usa `RecordingNotifier`: guarda los mensajes en
memoria para que las pruebas los lean (`messages`) y puedan aislarse entre casos (`reset`). El envío
real por SMTP (soporte@autoken.es) se cablea después (spec S1.4 §6): implementará esta misma
interfaz y se seleccionará en la factoría (`notifications.get_notifier`), sin tocar el dominio.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

# Tope de mensajes que retiene el grabador en memoria: es una ayuda de test/dev, no un buzón; si se
# usara fuera de test (envío diferido) no debe crecer sin límite. Los más antiguos se descartan.
_RECORDING_MAX_MESSAGES = 1000


@dataclass(frozen=True)
class Message:
    """Un mensaje de notificación (hoy, un email). `to` es el destinatario."""

    to: str
    subject: str
    body: str
    kind: str = "generic"


class Notifier(ABC):
    """Puerto de salida de notificaciones. El transporte concreto lo aporta cada backend."""

    @abstractmethod
    def send(self, message: Message) -> None:
        """Envía (o registra) un mensaje."""


class RecordingNotifier(Notifier):
    """Backend en memoria (test/dev): acumula los mensajes en `messages` en vez de enviarlos.

    No es un `Notifier` de producción: existe para poder verificar en las pruebas que se avisó a
    quien tocaba (y a nadie más). El SMTP real (spec §6) será otro `Notifier` que sí envíe.
    """

    def __init__(self) -> None:
        # Cola acotada (los más antiguos se descartan): retener sin límite sería una fuga si el
        # grabador se usara fuera de test. En test se vacía con `reset` entre casos.
        self._messages: deque[Message] = deque(maxlen=_RECORDING_MAX_MESSAGES)

    @property
    def messages(self) -> list[Message]:
        """Mensajes registrados hasta ahora (en orden de envío)."""
        return list(self._messages)

    def send(self, message: Message) -> None:
        self._messages.append(message)

    def reset(self) -> None:
        """Vacía los mensajes acumulados (aislamiento entre pruebas)."""
        self._messages.clear()
