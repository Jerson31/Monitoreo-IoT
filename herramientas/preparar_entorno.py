"""Prepara la configuración local de InfluxDB sin instalar ni iniciar servicios."""

from pathlib import Path
import secrets


def main():
    archivo = Path(__file__).resolve().parent.parent / ".env"
    if archivo.exists():
        print(".env ya existe. Se conservó la configuración y sus credenciales.")
        return

    configuracion = {
        "INFLUX_USERNAME": "ta3admin",
        "INFLUX_PASSWORD": secrets.token_hex(10),
        "INFLUX_ORG": "TA3",
        "INFLUX_BUCKET": "temperaturas",
        "INFLUX_TOKEN": secrets.token_hex(32),
        "INFLUX_RETENTION": "7d",
        "INFLUX_URL": "http://127.0.0.1:8086",
    }
    # "x" evita sustituir por accidente un archivo creado simultáneamente.
    with archivo.open("x", encoding="utf-8") as salida:
        salida.write("# Configuración local de la TA3. Docker Compose lee este archivo.\n")
        salida.write("# Conserva las claves; no se incluyen en Git.\n")
        for clave, valor in configuracion.items():
            salida.write(f"{clave}={valor}\n")
    print("Configuración creada en .env. Organización: TA3. Bucket: temperaturas.")
    print("Usuario: ta3admin. Consulta INFLUX_PASSWORD en VS Code para iniciar sesión.")


if __name__ == "__main__":
    main()
