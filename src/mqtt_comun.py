"""Funciones compartidas de conexión MQTT para el prototipo local."""

from threading import Event


def conectar(cliente_id, broker, puerto, al_recibir=None, suscripcion=None):
    """Conecta y espera la confirmación del broker (y de la suscripción)."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise RuntimeError(
            "Falta Paho MQTT. Usa el Python de .venv después de instalar requirements.txt."
        ) from None

    listo = Event()
    errores = []
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cliente_id)
    cliente.connect_timeout = 5.0

    def al_conectar(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            errores.append(f"EMQX rechazó la conexión: {reason_code}")
            listo.set()
        elif suscripcion:
            # Se vuelve a suscribir si Paho reconecta tras una interrupción.
            resultado, _ = client.subscribe(suscripcion, qos=1)
            if resultado != mqtt.MQTT_ERR_SUCCESS:
                errores.append(f"No se pudo solicitar la suscripción: {resultado}")
                listo.set()
        else:
            listo.set()

    def al_suscribir(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            errores.append("EMQX rechazó la suscripción.")
        listo.set()

    cliente.on_connect = al_conectar
    cliente.on_subscribe = al_suscribir
    if al_recibir:
        cliente.on_message = al_recibir

    try:
        cliente.connect(broker, puerto, keepalive=30)
        cliente.loop_start()  # Atiende mensajes y confirmaciones en segundo plano.
        if not listo.wait(timeout=8):
            raise RuntimeError("El broker no confirmó la conexión o suscripción.")
        if errores:
            raise RuntimeError(errores[0])
        return cliente
    except Exception:
        cerrar(cliente)
        raise


def publicar(cliente, topico, mensaje):
    """QoS 1: espera la confirmación de recepción del broker."""
    resultado = cliente.publish(topico, mensaje, qos=1, retain=False)
    if resultado.rc != 0:
        raise RuntimeError(f"No se pudo enviar el mensaje MQTT: código {resultado.rc}")
    resultado.wait_for_publish(timeout=8)
    if not resultado.is_published():
        raise RuntimeError("El broker no confirmó la publicación a tiempo.")


def cerrar(cliente):
    cliente.disconnect()
    cliente.loop_stop()
