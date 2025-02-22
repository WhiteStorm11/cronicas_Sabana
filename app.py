from flask import Flask, request, jsonify, send_from_directory
import json
import os
import requests
import time
import re 

app = Flask(__name__)

# URLs y Configuraciones
SD_API_URL = "https://e5380dbaca7d21a6b0.gradio.live/sdapi/v1/txt2img"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent"
GEMINI_API_KEY = "AIzaSyAbJLulvkEmB01fP_3shMhPMX2icrmkXuI"

DATA_FILE = "data/relatos.json"
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

# Función para cargar datos con manejo de errores
def cargar_datos():
    try:
        if not os.path.exists(DATA_FILE):
            guardar_datos([])
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, IOError):
        print("⚠️ Error al leer el archivo JSON. Creando uno nuevo.")
        guardar_datos([])
        return []

# Función para guardar datos
def guardar_datos(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4)
    except IOError:
        print("❌ Error al guardar datos en el archivo JSON.")

# Función para reformular prompts antes de enviarlos a Gemini
def reformar_prompt(prompt):
    palabras_prohibidas = {
        r"\b(batalla|combate|pelea|lucha|conflicto|guerra)\b": "encuentro épico",
        r"\b(derrotar|vencer|aniquilar|destruir)\b": "superar un desafío",
        r"\b(ataque|golpe|agresión)\b": "movimiento dinámico",
        r"\b(sangre|herida|violencia)\b": "",
    }

    for palabra, reemplazo in palabras_prohibidas.items():
        prompt = re.sub(palabra, reemplazo, prompt, flags=re.IGNORECASE)

    return prompt

def mejorar_prompt(prompt_usuario, max_reintentos=3):
    prompt_usuario = reformar_prompt(prompt_usuario)  # Reformular antes de enviar

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [ {
            "parts": [{"text": f"""
            Dado el siguiente mensaje de un usuario sin conocimientos técnicos, genera un prompt detallado para una IA de imágenes, y también un prompt negativo para evitar elementos no deseados.
            Mensaje del usuario: {prompt_usuario}

            Responde solo con un JSON en este formato:
            {{"prompt": "Aquí va el prompt detallado", "negative_prompt": "Aquí va el prompt negativo"}}
            """}]
        }],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500}
    }

    for intento in range(max_reintentos):
        try:
            response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", headers=headers, json=payload)
            response_json = response.json()

            if "candidates" in response_json:
                candidate = response_json["candidates"][0]
                
                if candidate.get("finishReason") == "SAFETY":
                    print(f"⚠️ Gemini bloqueó la respuesta. Reformulando intento {intento+1}...")
                    prompt_usuario = reformar_prompt(prompt_usuario)  # 🔄 Intentar reformular otra vez
                    time.sleep(5)
                    continue  

                generated_text = candidate["content"]["parts"][0]["text"]
                generated_text = re.sub(r"```json\n(.*?)\n```", r"\1", generated_text, flags=re.DOTALL)

                try:
                    resultado = json.loads(generated_text)
                    prompt_final = resultado.get("prompt", prompt_usuario)
                    negative_prompt_final = resultado.get("negative_prompt", "low quality, blurred, ugly, distorted")
                    
                    print(f"✅ Prompt final generado: {prompt_final}")
                    print(f"🚫 Negative Prompt generado: {negative_prompt_final}")

                    return prompt_final, negative_prompt_final
                except json.JSONDecodeError:
                    print("⚠️ Error al parsear respuesta de Gemini. Usando el prompt original.")
                    return prompt_usuario, "low quality, blurred, ugly, distorted"

        except Exception as e:
            print(f"❌ Error al conectar con Gemini: {e}")

    print("❌ No se pudo obtener un prompt mejorado después de varios intentos.")
    return prompt_usuario, "low quality, blurred, ugly, distorted"


@app.route("/generar-ilustracion", methods=["POST"])
def generar_ilustracion():
    data = request.json
    prompt_usuario = data.get("prompt", "")

    if not prompt_usuario:
        return jsonify({"error": "Descripción vacía"}), 400

    prompt_mejorado, negative_prompt = mejorar_prompt(prompt_usuario)

    # Imprimir el prompt que se enviará a Stable Diffusion
    print(f"🎨 Prompt enviado a Stable Diffusion: {prompt_mejorado}")
    print(f"🚫 Negative Prompt: {negative_prompt}")

    payload = {
    "prompt": f"A high-resolution photo of {prompt_mejorado}, ultra-detailed, hyperrealistic, 8K, cinematic lighting",
    "negative_prompt": f"{negative_prompt}, cartoon, anime, illustration, drawing, 2D, low quality, blurry",
    "steps": 60,
    "cfg_scale": 12,
    "width": 1024,
    "height": 1024,
    "sampler_name": "DPM++ 2M Karras"
    }


    try:
        response = requests.post(SD_API_URL, json=payload)
        response_json = response.json()

        if "images" in response_json:
            return jsonify({"image_base64": response_json["images"][0]})
        else:
            print("⚠️ Respuesta inesperada de Stable Diffusion:", response_json)
            return jsonify({"error": "No se pudo generar la imagen"}), 500

    except Exception as e:
        print(f"❌ Error al generar imagen con Stable Diffusion: {e}")
        return jsonify({"error": str(e)}), 500


# 📌 Ruta principal
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

# 📂 Endpoint para gestionar relatos
@app.route("/relatos", methods=["GET", "POST"])
def gestionar_relatos():
    if request.method == "GET":
        return jsonify(cargar_datos())

    elif request.method == "POST":
        data = request.json
        relatos = cargar_datos()
        relatos.append(data)
        guardar_datos(relatos)
        return jsonify({"message": "Relato agregado"}), 201

# 📌 Endpoint para probar solo la generación de prompts
@app.route("/test-gemini", methods=["POST"])
def test_gemini():
    data = request.json
    prompt_usuario = data.get("prompt", "")

    if not prompt_usuario:
        return jsonify({"error": "Descripción vacía"}), 400

    prompt_mejorado, negative_prompt = mejorar_prompt(prompt_usuario)
    
    return jsonify({
        "prompt_mejorado": prompt_mejorado,
        "negative_prompt": negative_prompt
    })

if __name__ == "__main__":
    app.run(debug=True)
