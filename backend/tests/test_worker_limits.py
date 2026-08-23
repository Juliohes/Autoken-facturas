"""Límites iniciales de concurrencia de workers R-044."""


def test_r044_separara_los_limites_de_produccion_y_background() -> None:
    from jobs.worker import BackgroundWorkerSettings, WorkerSettings

    assert WorkerSettings.max_jobs == 4
    assert BackgroundWorkerSettings.max_jobs == 1
