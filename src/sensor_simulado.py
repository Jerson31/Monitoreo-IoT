

import argparse
from datetime import datetime, timezone
import json
import random
import os
import socket
import signal
import time

from configuracion import INTERVALO_SEGUNDOS, NODOS
from mqtt_comun import cerrar, conectar, publicar


class NodoTemperatura:
    """Conserva la temperatura anterior para evitar saltos aleatorios bruscos."""

    def __init__(self, sensor, semilla=None):
        self.sensor = sensor
        self.config = NODOS[sensor]
        self.azar = random.Random(semilla)
        self.temperatura = self.config["base"]

    def leer(self, numero):
        # Cada ciclo dura tres minutos: normal, calentamiento y recuperación.
        # Es un escenario programado; no representa una puerta física detectada.
        fase = ((numero - 1) * INTERVALO_SEGUNDOS) % 180
        objetivo = self.config["base"]
        if self.sensor == "ALM-02" and 60 <= fase < 150:
            objetivo = 29.4
        # Se aproxima al objetivo con una pequeña variación por lectura.
        cambio = 0.22 * (objetivo - self.temperatura) + self.azar.uniform(-0.12, 0.12)
        self.temperatura = max(self.config["minimo"], min(self.config["maximo"], self.temperatura + cambio))
        return {
            "sensor": self.sensor, "zona": self.config["zona"],
            "temperatura_c": round(self.temperatura, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "lectura": numero, "origen": "simulado",
        }


def main():
    # Las opciones permiten elegir el nodo y cuántas lecturas queremos observar.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lecturas", type=int, default=0,
        help="Cantidad de lecturas por nodo; 0 significa ejecución continua.",
    )
    parser.add_argument(
        "--sensor", choices=["ambos", *NODOS], default="ambos",
        help="Simular ambos nodos o ejecutar uno de ellos por separado.",
    )
    parser.add_argument("--mqtt", action="store_true", help="Enviar lecturas a EMQX.")
    parser.add_argument("--broker", default="127.0.0.1", help="Dirección del broker MQTT.")
    parser.add_argument("--puerto", type=int, default=1883, help="Puerto MQTT.")
    parser.add_argument("--semilla", type=int, help="Permite repetir el perfil de temperatura de una prueba.")
    args = parser.parse_args()
    if args.lecturas < 0:
        parser.error("La cantidad de lecturas debe ser mayor o igual que cero.")
    if not 1 <= args.puerto <= 65535:
        parser.error("El puerto debe estar entre 1 y 65535.")

    intervalo = float(INTERVALO_SEGUNDOS)
    sensores = list(NODOS) if args.sensor == "ambos" else [args.sensor]
    nodos = {sensor: NodoTemperatura(sensor, args.semilla) for sensor in sensores}
    numero = 0
    clientes = {}

    def detener(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, detener)  # Permite detener limpiamente desde Docker.

    try:
        if args.mqtt:
            for sensor in sensores:
                # Una conexión MQTT distinta por nodo, visible en el panel de EMQX.
                clientes[sensor] = conectar(
                    f"ta3-{sensor}-{socket.gethostname()}-{os.getpid()}", args.broker, args.puerto
                )
            print(f"Conectados {len(clientes)} nodos a {args.broker}:{args.puerto}.", flush=True)
        siguiente = time.monotonic()
        while args.lecturas == 0 or numero < args.lecturas:
            time.sleep(max(0.0, siguiente - time.monotonic()))
            numero += 1
            # Cada contenedor ejecuta un nodo; la opción ambos sirve para pruebas locales.
            for sensor in sensores:
                mensaje = json.dumps(nodos[sensor].leer(numero), ensure_ascii=False)
                if args.mqtt:
                    # El tópico identifica el origen para que otros programas se suscriban.
                    topico = f"ta3/almacen/{sensor}/temperatura"
                    publicar(clientes[sensor], topico, mensaje)
                    print(f"PUBLICADO {topico} {mensaje}", flush=True)
                else:
                    print(mensaje, flush=True)
            siguiente += intervalo
            # Evita emitir una ráfaga si la computadora se suspendió.
            if siguiente < time.monotonic():
                siguiente = time.monotonic() + intervalo
    except KeyboardInterrupt:
        print("Simulación detenida.", flush=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error MQTT: {error}. Comprueba que EMQX esté activo.") from None
    finally:
        for cliente in clientes.values():
            cerrar(cliente)


if __name__ == "__main__":
    # Empieza la simulación cuando ejecutamos este archivo con Python.
    main()
