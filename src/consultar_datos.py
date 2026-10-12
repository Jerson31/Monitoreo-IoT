"""Consulta las temperaturas conservadas en InfluxDB, incluso con el simulador detenido."""

import argparse
import json

from influx_comun import cargar_configuracion, consultar


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutos", type=int, default=15, help="Consultar este periodo reciente.")
    parser.add_argument("--limite", type=int, default=20, help="Máximo de temperaturas mostradas.")
    args = parser.parse_args()
    if args.minutos <= 0 or args.limite <= 0:
        parser.error("Minutos y límite deben ser positivos.")
    try:
        config = cargar_configuracion()
        registros = consultar(config, args.minutos, args.limite)
        print(f"CONSULTA INFLUXDB. Bucket: {config['INFLUX_BUCKET']}. Últimos {args.minutos} minutos.")
        for registro in registros:
            print("REGISTRO " + json.dumps(registro, ensure_ascii=False))
        print(f"Resultado: {len(registros)} temperaturas almacenadas (máximo {args.limite}).")
        if not registros:
            print("No hay temperaturas en ese periodo. Inicia primero el receptor y después el emisor.")
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Error de consulta: {error}") from None


if __name__ == "__main__":
    main()
