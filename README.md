# Monitoreo térmico de un almacén

Este proyecto representa el monitoreo ambiental de un centro de distribución
de detergentes líquidos y jabones en envases cerrados. Permite observar la
temperatura de dos zonas, reconocer cuándo superan 28 °C y revisar su historial.
Es la versión definitiva del prototipo TA3.

**Zona A:** almacenamiento. **Zona B:** recepción y despacho. El responsable del
almacén usa el dashboard para identificar qué área requiere revisión y en qué
momento ocurrió un aumento de temperatura.

El almacén y las mediciones son simulados. MQTT, la red virtual, la base de datos
y el dashboard funcionan con software real. El límite de 28 °C es un supuesto
del proyecto, no una norma de conservación de un producto.

## Por dónde empezar

1. Lee `docs/CONTEXTO_Y_SOLUCION.md` para explicar el problema y la finalidad.
2. Sigue `docs/GUIA_DE_USO.md` para iniciar, observar y detener el sistema.
3. Usa `docs/EVIDENCIAS_Y_RUBRICA.md` para organizar la entrega.

## Iniciar la versión definitiva

Desde esta carpeta, con Docker Desktop abierto:

```powershell
docker compose build receptor
docker compose up -d
docker compose ps
```

Si ya tienes los servicios funcionando, estos comandos aplican las actualizaciones.
Los contenedores nuevos esperan a que el receptor esté disponible.

Paneles locales:

- Dashboard: http://localhost:3000/
- Broker EMQX: http://localhost:18083/
- Base de datos InfluxDB: http://localhost:8086/

En Grafana busca **Monitoreo térmico del almacén** dentro de **TA3 IoT**. Completa
el campo **Equipo** con el nombre real de tu grupo. El dashboard muestra la
temperatura, el estado por zona, el historial, la antigüedad de cada dato y una tabla.

## Organización

| Carpeta o archivo | Para qué sirve |
|---|---|
| `src/` | Código definitivo de nodos, MQTT, almacenamiento y consulta. |
| `grafana/` | Conexión a InfluxDB y único dashboard de la versión definitiva. |
| `docs/` | Contexto, uso y evidencias. |
| `herramientas/` | Preparación inicial y verificación integral. |
| `dependencias/` | Paquete oficial Paho MQTT para construir la imagen sin descargarlo otra vez. |
| `evidencias/` | Resultado de la verificación y espacio para capturas reales. |
| `compose.yaml` | Los seis servicios y su red virtual. |
| `Dockerfile` | Imagen compartida por ambos nodos y el receptor. |
| `.env` | Credenciales locales existentes; Docker Compose las lee. |
| `.venv/` | Python de Windows para consultas y comprobaciones opcionales. |

Las guías por etapas y pruebas anteriores se conservaron fuera de esta carpeta,
en `../TA3_archivo_desarrollo/`. Son historial; la referencia actual es este README.

## Código que conviene comprender

- `src/configuracion.py`: zonas, rangos, intervalo de diez segundos y umbral.
- `src/sensor_simulado.py`: evolución de la temperatura y publicación por nodo.
- `src/mqtt_comun.py`: conexión, suscripción y confirmación MQTT con QoS 1.
- `src/almacenar_mqtt.py`: recibe, valida y guarda las lecturas.
- `src/influx_comun.py`: configuración, formato de datos y API de InfluxDB.
- `src/consultar_datos.py`: consulta los registros conservados.

## Verificar y detener

```powershell
.\.venv\Scripts\python.exe herramientas/revisar_sistema.py
```

Esta comprobación consulta los servicios reales, la red, los mensajes, la base
de datos y las consultas del dashboard. Guarda su resultado en `evidencias/`.

Para detener primero los emisores y después el resto, conservando los datos:

```powershell
docker compose stop nodo_a nodo_b
docker compose stop receptor grafana influxdb emqx
```

No uses `down -v` para una parada normal: elimina los volúmenes de datos.
