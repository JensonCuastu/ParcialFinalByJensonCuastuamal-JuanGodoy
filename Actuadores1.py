from machine import Pin, PWM
import network
import urequests
import time

# === Pines del carrito ===
PIN_ENA, PIN_IN1, PIN_IN2 = 10, 12, 11
PIN_ENB, PIN_IN3, PIN_IN4 = 13, 14, 15

# === Velocidades ===
VELOCIDAD = 65000
VELOCIDAD_GIRO = 60000
VELOCIDAD_GIRO_RAPIDA = 65535
VELOCIDAD_LENTA = 60000

class MotorController:
    def __init__(self):
        self.ena = PWM(Pin(PIN_ENA)); self.ena.freq(1000)
        self.in1 = Pin(PIN_IN1, Pin.OUT); self.in2 = Pin(PIN_IN2, Pin.OUT)
        self.enb = PWM(Pin(PIN_ENB)); self.enb.freq(1000)
        self.in3 = Pin(PIN_IN3, Pin.OUT); self.in4 = Pin(PIN_IN4, Pin.OUT)

    def adelante(self): self._mover(1, 0, 1, 0, VELOCIDAD, VELOCIDAD, 2.5)
    def atras(self): self._mover(0, 1, 0, 1, VELOCIDAD, VELOCIDAD, 2.5)
    def izquierda(self): self._mover(1, 0, 0, 1, VELOCIDAD_GIRO, VELOCIDAD_GIRO, 0.1)
    def derecha(self): self._mover(0, 1, 1, 0, VELOCIDAD_GIRO, VELOCIDAD_GIRO, 0.1)
    def giro_rapido_izquierda(self): self._mover(1, 0, 0, 1, VELOCIDAD_GIRO_RAPIDA, VELOCIDAD_GIRO_RAPIDA, 0.3)
    def giro_rapido_derecha(self): self._mover(0, 1, 1, 0, VELOCIDAD_GIRO_RAPIDA, VELOCIDAD_GIRO_RAPIDA, 0.3)
    def adelante_lento(self): self._mover(1, 0, 1, 0, VELOCIDAD_LENTA, VELOCIDAD_LENTA, 0.1)
    def atras_lento(self): self._mover(0, 1, 0, 1, VELOCIDAD_LENTA, VELOCIDAD_LENTA, 0.1)
    def stop(self): self._mover(0, 0, 0, 0, 0, 0, 0)

    def _mover(self, in1, in2, in3, in4, ena_speed, enb_speed, duracion):
        self.in1.value(in1); self.in2.value(in2)
        self.in3.value(in3); self.in4.value(in4)
        self.ena.duty_u16(ena_speed); self.enb.duty_u16(enb_speed)
        time.sleep(duracion)
        self.stop()

# === Brazo robótico ===
def angulo_a_duty_ns(angulo): return int((angulo / 180) * 2000000 + 500000)

def mover_suave(servo, angulo_actual, angulo_final, paso=0.25, delay=0.015):
    pasos = int(abs(angulo_final - angulo_actual) / paso)
    for i in range(pasos + 1):
        angulo = angulo_actual + i * paso if angulo_final > angulo_actual else angulo_actual - i * paso
        servo.duty_ns(angulo_a_duty_ns(angulo))
        time.sleep(delay)
    return angulo

# === Inicializar servos ===
codo = PWM(Pin(16)); codo.freq(50)
hombro = PWM(Pin(17)); hombro.freq(50)
base = PWM(Pin(18)); base.freq(50)

angulo_codo_actual = 90
angulo_hombro_actual = 180
angulo_base_actual = 95
posicion_actual = "porinicio"

# === Posiciones del brazo ===
posiciones = {
    "porinicio": {"codo": 90, "hombro": 180, "base": 95},
    "posver": {"codo": 100, "hombro": 130, "base": 95},
    "posrecoger": {"codo": 70, "hombro": 175, "base": 95}
}

def mover_a_posicion(nombre_posicion):
    global angulo_codo_actual, angulo_hombro_actual, angulo_base_actual, posicion_actual
    if ((posicion_actual == "posver" and nombre_posicion == "posrecoger") or 
        (posicion_actual == "posrecoger" and nombre_posicion == "posver")):
        inter = posiciones["porinicio"]
        angulo_codo_actual = mover_suave(codo, angulo_codo_actual, inter["codo"])
        angulo_hombro_actual = mover_suave(hombro, angulo_hombro_actual, inter["hombro"])
        angulo_base_actual = mover_suave(base, angulo_base_actual, inter["base"])
        posicion_actual = "porinicio"
        time.sleep(0.5)
    destino = posiciones[nombre_posicion]
    angulo_codo_actual = mover_suave(codo, angulo_codo_actual, destino["codo"])
    angulo_hombro_actual = mover_suave(hombro, angulo_hombro_actual, destino["hombro"])
    angulo_base_actual = mover_suave(base, angulo_base_actual, destino["base"])
    posicion_actual = nombre_posicion

# === Configuración de red ===
SSID = "Familia_Barragan"
PASSWORD = "Barragan2025"
SERVER_IP = "192.168.20.166"
SERVER_PORT = 5000

def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            pass
    print("Conectado a WiFi:", wlan.ifconfig())

# === Diccionario de comandos ===
motor = MotorController()
comandos_validos = {
    "adelante": motor.adelante,
    "atras": motor.atras,
    "izquierda": motor.izquierda,
    "derecha": motor.derecha,
    "stop": motor.stop,
    "adelante_lento": motor.adelante_lento,
    "atras_lento": motor.atras_lento,
    "giro_rapido_izquierda": motor.giro_rapido_izquierda,
    "giro_rapido_derecha": motor.giro_rapido_derecha,
    "porinicio": lambda: mover_a_posicion("porinicio"),
    "posver": lambda: mover_a_posicion("posver"),
    "posrecoger": lambda: mover_a_posicion("posrecoger")
}

# === Obtener comando desde el servidor Flask ===
def obtener_comando():
    try:
        url = f"http://{SERVER_IP}:{SERVER_PORT}/mensaje_actuadores"
        res = urequests.get(url)
        comando = res.text.strip()
        res.close()
        return comando if comando in comandos_validos else None
    except:
        return None

# === Ejecución principal ===
conectar_wifi()
while True:
    comando = obtener_comando()
    if comando:
        print("[PICO] Ejecutando:", comando)
        comandos_validos[comando]()
    time.sleep(0.5)
