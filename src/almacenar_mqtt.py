"""Recibe las temperaturas MQTT y guarda cada lectura automáticamente en InfluxDB."""

import argparse
import json
import os
import socket
import signal
from pathlib import Path
from queue import Empty, Queue
import time

from influx_comun import cargar_configuracion, consultar, guardar
from mqtt_comun import cerrar, conectar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mensajes", type=int, default=0, help="0: almacenamiento continuo.")
    parser.add_argument("--broker", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=1883)
    parser.add_argument("--timeout", type=float, default=60, help="Plazo para una prueba finita.")
    parser.add_argument("--senal-listo", type=Path, help="Archivo de disponibilidad para Docker.")
    args = parser.parse_args()
    if args.mensajes < 0 or args.timeout <= 0 or not 1 <= args.puerto <= 65535:
        parser.error("Mensajes >= 0, timeout > 0 y puerto entre 1 y 65535.")
    mensajes = Queue()

    def al_recibir(client, userdata, mensaje):
        # El hilo MQTT solo encola; el programa principal valida y escribe.
        mensajes.put((mensaje.topic, mensaje.payload))

    cliente = None
    guardados = 0
    def detener(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, detener)
    try:
        if args.senal_listo:
            args.senal_listo.unlink(missing_ok=True)
        config = cargar_configuracion()
        consultar(config, limite=1)  # Comprueba servicio, token y bucket antes de recibir.
        cliente = conectar(f"ta3-receptor-{socket.gethostname()}-{os.getpid()}", args.broker, args.puerto,
                           al_recibir=al_recibir, suscripcion="ta3/almacen/+/temperatura")
        if args.senal_listo:
            args.senal_listo.write_text("listo\n", encoding="utf-8")
        print(f"ALMACENAMIENTO LISTO. Bucket: {config['INFLUX_BUCKET']}. Esperando lecturas...", flush=True)
        fin = time.monotonic() + args.timeout if args.mensajes else None
        while args.mensajes == 0 or guardados < args.mensajes:
            if fin is not None and time.monotonic() >= fin:
                raise RuntimeError(f"Tiempo agotado: guardados {guardados}/{args.mensajes} mensajes.")
            try:
                topico, contenido = mensajes.get(timeout=1)
            except Empty:
                continue
            try:
                datos = json.loads(contenido.decode("utf-8"))
                guardar(config, topico, datos)
            except ValueError as error:
                print(f"DESCARTADO: {error}", flush=True)
                continue
            # GUARDADO aparece solo después de la confirmación HTTP de InfluxDB.
            guardados += 1
            print("GUARDADO " + json.dumps({"topico": topico, "datos": datos}, ensure_ascii=False), flush=True)
        print(f"Prueba terminada: {guardados} escrituras confirmadas por InfluxDB.", flush=True)
    except KeyboardInterrupt:
        print(f"Almacenamiento detenido: {guardados} escrituras confirmadas.", flush=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error de almacenamiento: {error}") from None
    finally:
        if args.senal_listo:
            args.senal_listo.unlink(missing_ok=True)
        if cliente is not None:
            cerrar(cliente)


if __name__ == "__main__":
    main()
