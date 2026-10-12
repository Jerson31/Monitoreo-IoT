"""Verifica la versión definitiva usando los servicios reales y conserva evidencia JSON."""

import base64
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
from influx_comun import cargar_configuracion, consultar, solicitar
from sensor_simulado import NodoTemperatura


def main():
    docker = shutil.which("docker") or r"C:\Users\51980\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe"
    def ejecutar(*argumentos):
        resultado = subprocess.run([docker, *argumentos], cwd=RAIZ,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        if resultado.returncode:
            raise RuntimeError("Falló Docker: " + resultado.stderr.strip())
        return resultado.stdout

    # Comprueba el perfil lógico sin esperar el tiempo de una exposición real.
    perfiles = {}
    for sensor in ("ALM-01", "ALM-02"):
        nodo = NodoTemperatura(sensor, semilla=7)
        valores = [nodo.leer(numero)["temperatura_c"] for numero in range(1, 37)]
        if any(abs(b - a) > 1 for a, b in zip(valores, valores[1:])):
            raise AssertionError("El perfil genera saltos superiores a 1 °C entre lecturas.")
        perfiles[sensor] = {"minimo": min(valores), "maximo": max(valores)}
    if perfiles["ALM-01"]["maximo"] > 28 or perfiles["ALM-02"]["maximo"] <= 28:
        raise AssertionError("El escenario no distingue una zona estable y otra con calentamiento.")

    esperados = {"nodo_a", "nodo_b", "receptor", "emqx", "influxdb", "grafana"}
    activos = set(ejecutar("compose", "ps", "--services", "--status", "running").splitlines())
    if not esperados.issubset(activos):
        raise RuntimeError("Faltan servicios activos: " + ", ".join(sorted(esperados - activos)))
    redes = []
    for servicio in sorted(esperados):
        identidad = ejecutar("compose", "ps", "-q", servicio).strip()
        conexiones = json.loads(ejecutar("inspect", "--format", "{{json .NetworkSettings.Networks}}", identidad))
        if "ta3_red_iot" not in conexiones:
            raise AssertionError(f"{servicio} está fuera de la red virtual.")
        redes.append(servicio)

    config = cargar_configuracion()
    publicados = {}
    guardados = {}
    plazo = time.monotonic() + 60
    while True:
        texto = ejecutar("compose", "logs", "--no-color", "--since", "2m", "nodo_a", "nodo_b", "receptor")
        for linea in texto.splitlines():
            if "PUBLICADO " in linea:
                dato = json.loads(linea.split("PUBLICADO ", 1)[1].split(" ", 1)[1])
                publicados[(dato["sensor"], dato["timestamp"])] = dato
            elif "GUARDADO " in linea:
                dato = json.loads(linea.split("GUARDADO ", 1)[1])["datos"]
                guardados[(dato["sensor"], dato["timestamp"])] = dato
        seleccion = []
        for sensor in ("ALM-01", "ALM-02"):
            seleccion.extend(sorted((dato for dato in publicados.values() if dato["sensor"] == sensor),
                                    key=lambda dato: dato["timestamp"])[-3:])
        if len(seleccion) == 6 and all(guardados.get((dato["sensor"], dato["timestamp"])) == dato for dato in seleccion):
            break
        if time.monotonic() > plazo:
            raise RuntimeError("No se observaron tres publicaciones y escrituras coincidentes por nodo.")
        time.sleep(1)
    registros = consultar(config, limite=1000)
    indice = {(dato["sensor"], datetime.fromisoformat(dato["timestamp"])): dato for dato in registros}
    for dato in seleccion:
        almacenado = indice[(dato["sensor"], datetime.fromisoformat(dato["timestamp"]))]
        for campo in ("sensor", "zona", "temperatura_c", "lectura", "origen"):
            if dato[campo] != almacenado[campo]:
                raise AssertionError("No coincide la publicación con el registro de InfluxDB.")

    valores_env = dict(linea.split("=", 1) for linea in (RAIZ / ".env").read_text().splitlines()
                       if linea and not linea.startswith("#") and "=" in linea)
    credencial = base64.b64encode((valores_env["INFLUX_USERNAME"] + ":" + valores_env["INFLUX_PASSWORD"]).encode()).decode()
    def grafana(ruta):
        peticion = Request("http://127.0.0.1:3000" + ruta, headers={"Authorization": "Basic " + credencial})
        with build_opener(ProxyHandler({})).open(peticion, timeout=10) as respuesta:
            return json.load(respuesta)
    salud = grafana("/api/datasources/uid/ta3-influx/health")
    if salud.get("status", "").lower() not in ("ok", "success"):
        raise AssertionError("Grafana no confirmó la conexión con InfluxDB.")
    dashboard = grafana("/api/dashboards/uid/ta3-almacen-simulado")["dashboard"]
    if dashboard["title"] != "Monitoreo térmico del almacén":
        raise RuntimeError("Grafana todavía no cargó el dashboard definitivo; espera y repite la comprobación.")
    consultas = 0
    for filtro in (".*", "ALM-01", "ALM-02"):
        for panel in dashboard["panels"]:
            for objetivo in panel.get("targets", []):
                consulta = objetivo["query"].replace("${bucket}", config["INFLUX_BUCKET"])
                consulta = consulta.replace("${sensor:regex}", filtro)
                consulta = "option v = {timeRangeStart: -15m, timeRangeStop: now(), windowPeriod: 10s}\n" + consulta
                respuesta = solicitar(config, "/api/v2/query", {"org": config["INFLUX_ORG"]},
                                      consulta, "application/vnd.flux")
                filas = list(csv.reader(linea for linea in respuesta.splitlines()
                                        if linea and not linea.startswith("#")))
                if len(filas) < 2 or not any(campo in filas[0] for campo in ("_value", "Temperatura")):
                    raise AssertionError(f"No hubo datos para el panel {panel['id']}.")
                consultas += 1
    recursos = [json.loads(linea) for linea in ejecutar("compose", "stats", "--no-stream", "--format", "{{json .}}").splitlines()
                if linea.strip()]
    evidencia = {
        "resultado": "correcto", "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "servicios_en_red": redes, "mensajes_coincidentes": seleccion,
        "dashboard": dashboard["title"], "conexion_grafana_influxdb": "correcta",
        "consultas_flux_comprobadas": consultas,
        "perfil_logico_sin_espera_real": perfiles, "recursos": recursos,
        "limite_de_verificacion": "Verifica servicios y consultas; la apariencia se revisa en el navegador.",
    }
    salida = RAIZ / "evidencias" / "verificacion_definitiva.json"
    salida.parent.mkdir(exist_ok=True)
    (salida.parent / "capturas").mkdir(exist_ok=True)
    salida.write_text(json.dumps(evidencia, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CORRECTO: 6 servicios en la red y 6 mensajes coincidentes entre nodos, receptor e InfluxDB.")
    print(f"CORRECTO: Grafana conectado; dashboard definitivo cargado; {consultas} consultas verificadas.")
    print("Resultado guardado en evidencias/verificacion_definitiva.json. Credenciales excluidas.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, AssertionError, ValueError, KeyError) as error:
        raise SystemExit(f"Verificación pendiente: {error}") from None
