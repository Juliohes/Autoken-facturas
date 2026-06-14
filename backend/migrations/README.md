# Migraciones Alembic

Migraciones de esquema de la base de datos (async). La URL de conexión se toma de
`DATABASE_URL` (config de la app), nunca de `alembic.ini`.

```bash
# Crear una revisión (autogenerada cuando haya modelos, a partir de S1.1)
alembic revision -m "descripcion"

# Aplicar / revertir
alembic upgrade head
alembic downgrade -1
```

Regla del plan (§2.4): toda migración debe implementar y testear su `downgrade`.
Los modelos y `Base.metadata` se enlazan en la tarea S1.1.
