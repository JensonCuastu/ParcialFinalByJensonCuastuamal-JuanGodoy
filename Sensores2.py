from machine import Pin, time_pulse_us, I2C
import machine
import network
import socket
import time
from ov7670_wrapper import *

# === CONFIGURACIÓN SENSOR ULTRASÓNICO ===
TRIG = Pin(17, Pin.OUT)
ECHO = Pin(16, Pin.IN)

def medir_distancia():
    TRIG.value(0)
    time.sleep_us(2)
    TRIG.value(1)
    time.sleep_us(10)
    TRIG.value(0)

    duracion = time_pulse_us(ECHO, 1, 30000)  # Timeout 30ms
    if duracion < 0:
        return None
    distancia_cm = (duracion / 2) / 29.1
    return distancia_cm

# === CONFIGURACIÓN CÁMARA OV7670 ===
data_pin_base = 0
pclk_pin_no = 8
mclk_pin_no = 9
href_pin_no = 12
vsync_pin_no = 13
reset_pin_no = 14
shutdown_pin_no = 15
sda_pin_no = 20
scl_pin_no = 21

def init_camera():
    i2c = I2C(0, freq=100000, scl=Pin(scl_pin_no), sda=Pin(sda_pin_no))
    cam = OV7670Wrapper(
        i2c_bus=i2c,
        mclk_pin_no=mclk_pin_no,
        pclk_pin_no=pclk_pin_no,
        data_pin_base=data_pin_base,
        vsync_pin_no=vsync_pin_no,
        href_pin_no=href_pin_no,
        reset_pin_no=reset_pin_no,
        shutdown_pin_no=shutdown_pin_no,
    )
    cam.wrapper_configure_yuv()
    cam.wrapper_configure_base()
    cam.wrapper_configure_size(OV7670_WRAPPER_SIZE_DIV4)  # 160x120
    cam.wrapper_configure_test_pattern(OV7670_WRAPPER_TEST_PATTERN_NONE)
    return cam

def send_all(sock, data):
    total_sent = 0
    while total_sent < len(data):
        sent = sock.send(data[total_sent:])
        if sent == 0:
            raise RuntimeError("Conexión rota durante el envío")
        total_sent += sent

def send_image(cam):
    width, height = 160, 120
    buf_size = width * height * 2  # YUV422
    buf = bytearray(buf_size)

    print("Capturando imagen...")
    cam.capture(buf)

    try:
        print("Conectando al servidor de imagen...")
        addr = socket.getaddrinfo(SERVER_IP, SERVER_PORT_IMG)[0][-1]
        s = socket.socket()
        s.connect(addr)
        print("Enviando imagen...")

        start_time = time.ticks_ms()

        send_all(s, len(buf).to_bytes(4, 'big'))
        chunk_size = 1024
        for i in range(0, len(buf), chunk_size):
            send_all(s, buf[i:i+chunk_size])

        end_time = time.ticks_ms()
        duracion_total = time.ticks_diff(end_time, start_time) / 1000
        print(f"Imagen enviada en {duracion_total:.2f} segundos.")
        s.close()
    except Exception as e:
        print("Error al enviar imagen:", e)

def enviar_distancia(distancia):
    try:
        addr = socket.getaddrinfo(SERVER_IP, SERVER_PORT_DIST)[0][-1]
        s = socket.socket()
        s.connect(addr)

        request = f"GET /mensaje_sensores?comando={distancia:.2f} HTTP/1.1\r\nHost: {SERVER_IP}\r\nConnection: close\r\n\r\n"
        s.send(request.encode())

        response = b""
        while True:
            data = s.recv(1024)
            if not data:
                break
            response += data
        s.close()

        print("Distancia enviada:", distancia, "cm")

    except Exception as e:
        print("Error al enviar distancia:", e)

# === CONFIGURACIÓN RED COMÚN ===
SSID = "Familia_Barragan"
PASSWORD = "Barragan2025"
SERVER_IP = "192.168.20.166"    # Cambia por IP de tu PC si es distinta
SERVER_PORT_IMG = 8080          # Puerto para envío de imágenes
SERVER_PORT_DIST = 5000         # Puerto para envío de distancia

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando a WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.2)
    print("Conectado a WiFi:", wlan.ifconfig())

# === FLUJO PRINCIPAL COMBINADO ===
connect_wifi()
camera = init_camera()
time.sleep(1)

while True:
    # Enviar distancia
    distancia = medir_distancia()
    if distancia is not None:
        enviar_distancia(distancia)
    else:
        print("Error: sin respuesta del sensor")

    # Enviar imagen
    send_image(camera)

    time.sleep(2)
