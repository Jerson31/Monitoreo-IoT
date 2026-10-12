"""Dos zonas del mismo almacén."""

INTERVALO_SEGUNDOS = 10
UMBRAL_C = 28.0

NODOS = {
    "ALM-01": {
        "zona": "zona_a", "nombre": "Almacenamiento",
        "minimo": 22.0, "maximo": 27.0, "base": 24.5,
    },
    "ALM-02": {
        "zona": "zona_b", "nombre": "Recepción y despacho",
        "minimo": 25.0, "maximo": 30.0, "base": 26.2,
    },
}
