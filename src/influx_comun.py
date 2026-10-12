"""Acceso a InfluxDB usando la biblioteca estándar de Python, sin instalar un SDK."""

import csv
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, ProxyHandler, Request

from configuracion import NODOS


def cargar_configuracion():
    """Lee .env sin imprimir credenciales; las variables de entorno tienen prioridad."""
    archivo = Path(__file__).resolve().parent.parent / ".env"
    valores = {}
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8-sig").splitlines():
            if linea.strip() and not linea.lstrip().startswith("#"):
                clave, separador, valor = linea.partition("=")
                if separador:
                    valores[clave.strip()] = valor.strip()
    claves = ("INFLUX_URL", "INFLUX_TOKEN", "INFLUX_ORG", "INFLUX_BUCKET")
    config = {clave: os.environ.get(clave, valores.get(clave, "")) for clave in claves}
    if not all(config.values()):
        raise ValueError("Falta configuración de InfluxDB. Revisa .env o ejecuta herramientas/preparar_entorno.py.")
    url = urlsplit(config["INFLUX_URL"])
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("INFLUX_URL debe ser una dirección HTTP/HTTPS sin credenciales.")
    return config


def solicitar(config, ruta, parametros, cuerpo, tipo):
    """Envía el token en una cabecera y devuelve únicamente la respuesta."""
    url = config["INFLUX_URL"].rstrip("/") + ruta + "?" + urlencode(parametros)
    peticion = Request(url, data=cuerpo.encode("utf-8"), method="POST", headers={
        "Authorization": "Token " + config["INFLUX_TOKEN"],
        "Content-Type": tipo,
        "Accept": "application/csv",
    })
    # El prototipo se comunica directamente con el servicio local.
    try:
        with build_opener(ProxyHandler({})).open(peticion, timeout=10) as respuesta:
            return respuesta.read().decode("utf-8")
    except HTTPError as error:
        detalles = {
            400: "Comprueba los datos o la consulta.",
            401: "Revisa el token en .env.",
            403: "El token no tiene los permisos necesarios.",
            404: "Revisa la organización y el bucket.",
        }
        raise RuntimeError(f"InfluxDB respondió HTTP {error.code}. " +
                           detalles.get(error.code, "Revisa el estado de InfluxDB.")) from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("No se pudo contactar con InfluxDB. Comprueba docker compose ps.") from None


def preparar_punto(topico, datos):
    """Comprueba el mensaje y lo convierte al formato Line Protocol de InfluxDB."""
    if not isinstance(datos, dict):
        raise ValueError("La lectura debe ser un objeto JSON.")
    sensor = datos.get("sensor")
    if not isinstance(sensor, str) or sensor not in NODOS:
        raise ValueError("Sensor desconocido.")
    zona = NODOS[sensor]["zona"]
    if datos.get("zona") != zona or datos.get("origen") != "simulado":
        raise ValueError("La zona o el origen no corresponde al nodo simulado.")
    if topico != f"ta3/almacen/{sensor}/temperatura":
        raise ValueError("El tópico no corresponde al sensor del mensaje.")
    temperatura = datos.get("temperatura_c")
    if type(temperatura) not in (int, float) or not math.isfinite(temperatura):
        raise ValueError("La temperatura debe ser un número finito.")
    lectura = datos.get("lectura")
    if type(lectura) is not int or not 1 <= lectura <= 2**63 - 1:
        raise ValueError("El número de lectura debe ser un entero positivo válido.")
    marca = datos.get("timestamp")
    if not isinstance(marca, str):
        raise ValueError("Falta la fecha y hora de la lectura.")
    momento = datetime.fromisoformat(marca)
    if momento.tzinfo is None:
        raise ValueError("La fecha debe indicar la zona horaria.")
    delta = momento.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    nanosegundos = ((delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds) * 1000
    return (f"temperatura,sensor={sensor},zona={zona},origen=simulado "
            f"temperatura_c={float(temperatura)},lectura={lectura}i {nanosegundos}")


def guardar(config, topico, datos):
    punto = preparar_punto(topico, datos)
    solicitar(config, "/api/v2/write", {
        "org": config["INFLUX_ORG"], "bucket": config["INFLUX_BUCKET"], "precision": "ns",
    }, punto, "text/plain; charset=utf-8")


def consultar(config, minutos=15, limite=20):
    """Devuelve una fila por temperatura, ordenada desde la más reciente."""
    if type(minutos) is not int or minutos <= 0 or type(limite) is not int or limite <= 0:
        raise ValueError("Minutos y límite deben ser enteros positivos.")
    # JSON genera un literal de texto válido para el nombre del bucket en Flux.
    consulta = f'''from(bucket: {json.dumps(config["INFLUX_BUCKET"])})
  |> range(start: -{minutos}m)
  |> filter(fn: (r) => r._measurement == "temperatura" and (r._field == "temperatura_c" or r._field == "lectura"))
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {limite})
  |> keep(columns: ["_time", "temperatura_c", "lectura", "sensor", "zona", "origen"])'''
    respuesta = solicitar(config, "/api/v2/query", {"org": config["INFLUX_ORG"]},
                          consulta, "application/vnd.flux")
    filas = csv.DictReader(io.StringIO("\n".join(
        linea for linea in respuesta.splitlines() if linea and not linea.startswith("#")
    )))
    return [{"sensor": fila["sensor"], "zona": fila["zona"],
             "temperatura_c": float(fila["temperatura_c"]), "lectura": int(fila["lectura"]),
             "timestamp": fila["_time"],
             "origen": fila["origen"]} for fila in filas]
