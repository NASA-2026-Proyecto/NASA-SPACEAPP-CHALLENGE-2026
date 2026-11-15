"""Punto de entrada de la API: `uvicorn app.main:app`.

Todas las rutas cuelgan de /api. El front se sirve aparte (nginx) y le reenvía /api/*,
así navegador, front y API comparten origen y no hace falta CORS.
"""

from app.factory import create_app

app = create_app()
