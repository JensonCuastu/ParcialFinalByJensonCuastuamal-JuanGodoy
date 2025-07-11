from flask import Flask, request, send_file, Response  
import threading
import socket
import numpy as np
import cv2
import os
import random
from cv2 import dnn_superres

app = Flask(__name__)

WIDTH, HEIGHT = 160, 120  # Resolución actualizada
YUV_FILE = "latest.yuv"
PNG_FILE = "latest.png"
EXPECTED_SIZE = WIDTH * HEIGHT * 2  # YUV422: 2 bytes por píxel
SWAP_UV = True  # Para corregir imagen azulada

# Superresolución con FSRCNN x4
sr = dnn_superres.DnnSuperResImpl_create()
sr.readModel("FSRCNN-small_x4.pb")  # Asegúrate de que este archivo esté en el mismo directorio
sr.setModel("fsrcnn", 4)

mensaje_actuadores = None
mensaje_sensores = None

def generar_datos_falsos():
    print("Generando imagen falsa por datos incompletos.")
    return bytes([random.randint(0, 255) for _ in range(EXPECTED_SIZE)])

def yuv422_to_png(yuv_data):
    try:
        yuv = np.frombuffer(yuv_data, dtype=np.uint8)
        if yuv.size != EXPECTED_SIZE:
            print("Advertencia: tamaño inesperado. Completando.")
            yuv_padded = bytearray(yuv_data)
            yuv_padded.extend([random.randint(0, 255) for _ in range(EXPECTED_SIZE - len(yuv_padded))])
            yuv = np.frombuffer(yuv_padded, dtype=np.uint8)

        yuv = yuv.reshape((HEIGHT, WIDTH, 2))
        bgr = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        for y in range(HEIGHT):
            for x in range(0, WIDTH, 2):
                y0 = yuv[y, x, 0]
                u  = yuv[y, x, 1]
                y1 = yuv[y, x+1, 0]
                v  = yuv[y, x+1, 1]

                if SWAP_UV:
                    u, v = v, u  # Corrección de color

                def convert(y, u, v):
                    c = y - 16
                    d = u - 128
                    e = v - 128
                    r = np.clip((298 * c + 409 * e + 128) >> 8, 0, 255)
                    g = np.clip((298 * c - 100 * d - 208 * e + 128) >> 8, 0, 255)
                    b = np.clip((298 * c + 516 * d + 128) >> 8, 0, 255)
                    return b, g, r

                bgr[y, x] = convert(y0, u, v)
                bgr[y, x+1] = convert(y1, u, v)

        # Aplicar superresolución FSRCNN x4
        enhanced = sr.upsample(bgr)
        rotated = cv2.rotate(enhanced, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.imwrite(PNG_FILE, enhanced)
        print("Imagen mejorada y guardada.")
    except Exception as e:
        print(f"Error en conversión YUV->PNG: {e}")

def tcp_receiver():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 8080))
        s.listen(1)
        print("Esperando imagen de la Pico W en el puerto 8080...")
        while True:
            conn, addr = s.accept()
            with conn:
                print(f"Conexión desde {addr}")
                try:
                    size_bytes = conn.recv(4)
                    if not size_bytes or len(size_bytes) < 4:
                        print("No se recibió tamaño.")
                        conn.sendall(b"NACK")
                        continue

                    size = int.from_bytes(size_bytes, 'big')
                    data = b''
                    while len(data) < size:
                        packet = conn.recv(min(1024, size - len(data)))
                        if not packet:
                            break
                        data += packet

                    if len(data) != size:
                        print(f"Incompleto ({len(data)} / {size}).")
                        conn.sendall(b"NACK")
                        continue
                    else:
                        conn.sendall(b"ACK")

                    yuv_data = data
                    with open(YUV_FILE, "wb") as f:
                        f.write(yuv_data)
                    print(f"Imagen recibida correctamente.")
                    yuv422_to_png(yuv_data)

                except Exception as e:
                    print(f"Error en recepción: {e}")
                    try:
                        conn.sendall(b"NACK")
                    except:
                        pass

@app.route('/')
def index():
    global mensaje_sensores  # Asegura acceso a la variable global
    mensaje_visible = mensaje_sensores if mensaje_sensores else ""
    return f'''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Control e Imagen</title>
    <style>
        body {{ background-color: #f2f2f2; text-align: center; font-family: Arial; }}
        h2 {{ margin-top: 30px; font-size: 32px; }}
        .mensaje {{ font-size: 24px; color: #333; margin-top: 20px; }}
        .boton {{ font-size: 30px; padding: 20px 40px; margin: 10px; border: none;
                 border-radius: 16px; background-color: #4CAF50; color: white; cursor: pointer; }}
        .boton:hover {{ background-color: #45a049; }}
        .stop {{ background-color: #d11a2a; }}
        .fastL, .fastR, .brazo {{ background-color: #007bff; }}
        .slowL, .slowB {{ background-color: #888888; }}
        .contenedor {{
            display: grid; grid-template-areas:
            ".     up     ."
            "left  stop  right"
            "slowL down  slowB"
            "fastL none  fastR"
            "brazoI brazoV brazoR";
            gap: 20px; justify-content: center; align-items: center; margin-top: 40px;
        }}
        .up {{ grid-area: up; }} .down {{ grid-area: down; }} .left {{ grid-area: left; }}
        .right {{ grid-area: right; }} .stop {{ grid-area: stop; }}
        .fastL {{ grid-area: fastL; }} .fastR {{ grid-area: fastR; }}
        .slowL {{ grid-area: slowL; }} .slowB {{ grid-area: slowB; }}
        .brazoI {{ grid-area: brazoI; }} .brazoV {{ grid-area: brazoV; }} .brazoR {{ grid-area: brazoR; }}
    </style>
    </head><body>
    <h2>Control del Carrito y Brazo</h2>
    <div class="mensaje"><strong>Último mensaje:</strong> <span id="mensaje-sensor">{mensaje_visible}</span></div>
    <div class="contenedor">
        <button class="boton up" onclick="enviar('adelante')">⬆️</button>
        <button class="boton left" onclick="enviar('izquierda')">⬅️</button>
        <button class="boton right" onclick="enviar('derecha')">➡️</button>
        <button class="boton down" onclick="enviar('atras')">⬇️</button>
        <button class="boton stop" onclick="enviar('stop')">⛔</button>
        <button class="boton slowL" onclick="enviar('adelante_lento')">🐢⬆️</button>
        <button class="boton slowB" onclick="enviar('atras_lento')">🐢⬇️</button>
        <button class="boton fastL" onclick="enviar('giro_rapido_izquierda')">⏪</button>
        <button class="boton fastR" onclick="enviar('giro_rapido_derecha')">⏩</button>
        <button class="boton brazoI" onclick="enviar('porinicio')">🔄 Inicio</button>
        <button class="boton brazoV" onclick="enviar('posver')">👁️ Ver</button>
        <button class="boton brazoR" onclick="enviar('posrecoger')">🤖 Recoger</button>
    </div>
    <h2>Última imagen recibida</h2>
    <img id="imagen-stream" src="/image" width="640" height="480" style="transform: rotate(0deg);"/>
    <script>
    function enviar(comando) {{
        fetch('/send', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
            body: 'msg=' + encodeURIComponent(comando)
        }}).then(response => {{
            if (!response.ok) {{
                console.error('Error al enviar comando');
            }}
        }});
    }}

    function actualizarImagen() {{
        const imagen = document.getElementById('imagen-stream');
        imagen.src = '/image?nocache=' + new Date().getTime();
    }}

    function actualizarMensaje() {{
        fetch('/mensaje')
        .then(response => response.text())
        .then(data => {{
            document.getElementById('mensaje-sensor').textContent = data;
        }});
    }}

    setInterval(actualizarImagen, 500);
    setInterval(actualizarMensaje, 500);
    </script>
    </body></html>
    '''
@app.route('/mensaje')
def mensaje():
    global mensaje_sensores
    return mensaje_sensores if mensaje_sensores else ""


@app.route('/image')
def image():
    if os.path.exists(PNG_FILE):
        return send_file(PNG_FILE, mimetype="image/png")
    else:
        return Response("No se ha recibido ninguna imagen todavía.", status=404)

@app.route('/send', methods=['POST'])
def send():
    global mensaje_actuadores
    mensaje_actuadores = request.form.get('msg', '')
    print(f"[PC] Comando para actuadores recibido desde la página: {mensaje_actuadores}")
    return '', 204

@app.route('/mensaje_actuadores')
def mensaje_act():
    global mensaje_actuadores
    msg = mensaje_actuadores or ""
    mensaje_actuadores = None
    return msg

@app.route('/mensaje_sensores')
def mensaje_sens():
    global mensaje_sensores
    nuevo_msg = request.args.get('comando')
    if nuevo_msg:
        mensaje_sensores = nuevo_msg
        print(f"[PC] Mensaje de sensores recibido vía GET: {nuevo_msg}")
        return "OK"
    return mensaje_sensores or ""

if __name__ == '__main__':
    threading.Thread(target=tcp_receiver, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)