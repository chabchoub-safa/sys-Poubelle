import RPi.GPIO as GPIO
import time
import cv2
import numpy as np
import tensorflow as tf
from mfrc522 import SimpleMFRC522
import firebase_admin
from firebase_admin import credentials, firestore
from RPLCD.i2c import CharLCD

# === LCD I2C ===
lcd = CharLCD('PCF8574', 0x27)  # Vérifie l'adresse I2C de ton écran (0x27 ou 0x3F)

# Initialisation Firebase
cred = credentials.Certificate("fir-294aa-firebase-adminsdk-dy9i5-bc22a82bcc.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Configuration GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

IR_PIN = 17
TRIG = 23
ECHO = 24
SERVO1 = 18
SERVO2 = 12
SERVO3 = 13

GPIO.setup(IR_PIN, GPIO.IN)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(SERVO1, GPIO.OUT)
GPIO.setup(SERVO2, GPIO.OUT)
GPIO.setup(SERVO3, GPIO.OUT)

servo1 = GPIO.PWM(SERVO1, 50)
servo2 = GPIO.PWM(SERVO2, 50)
servo3 = GPIO.PWM(SERVO3, 50)

servo1.start(7.5)
servo2.start(7.5)
servo3.start(7.5)

reader = SimpleMFRC522()

# Modèles IA
detection_interpreter = tf.lite.Interpreter(model_path='models100/detection_model.tflite')
detection_interpreter.allocate_tensors()
detection_input = detection_interpreter.get_input_details()
detection_output = detection_interpreter.get_output_details()

classification_interpreter = tf.lite.Interpreter(model_path='models100/classification_model.tflite')
classification_interpreter.allocate_tensors()
class_input = classification_interpreter.get_input_details()
class_output = classification_interpreter.get_output_details()

def lcd_display(line1="", line2=""):
    lcd.clear()
    lcd.write_string(line1[:16])
    lcd.crlf()
    lcd.write_string(line2[:16])

def detect_distance(timeout=1):
    GPIO.output(TRIG, False)
    time.sleep(0.05)
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start_time = time.time()
    while GPIO.input(ECHO) == 0:
        if time.time() - start_time > timeout:
            return -1
        pulse_start = time.time()

    while GPIO.input(ECHO) == 1:
        if time.time() - pulse_start > timeout:
            return -1
        pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

def rotate_servo(servo, angle):
    duty = angle / 18 + 2.5
    servo.ChangeDutyCycle(duty)
    time.sleep(0.5)
    servo.ChangeDutyCycle(7.5)

def capture_image():
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    return cv2.resize(frame, (128, 128))

def run_detection(image):
    img = np.expand_dims(image.astype(np.float32) / 255.0, axis=0)
    detection_interpreter.set_tensor(detection_input[0]['index'], img)
    detection_interpreter.invoke()
    result = detection_interpreter.get_tensor(detection_output[0]['index'])[0][0]
    return result > 0.5

def run_classification(image):
    img = np.expand_dims(image.astype(np.float32) / 255.0, axis=0)
    classification_interpreter.set_tensor(class_input[0]['index'], img)
    classification_interpreter.invoke()
    result = classification_interpreter.get_tensor(class_output[0]['index'])[0]
    return "plastique" if np.argmax(result) == 0 else "verre"

def send_to_firebase(binId, quantity, bottle_type, user_id):
    doc = {
        'binId': binId,
        'quantity': quantity,
        'type': bottle_type,
        'userId': user_id
    }
    db.collection("bottles").add(doc)
    print(f"✅ Envoyé à Firebase : {doc}")

def check_rfid_in_firestore(rfid_id):
    users_ref = db.collection("users")
    query = users_ref.where("rfid", "==", rfid_id).get()
    return query[0].to_dict().get("userId") if query else None

# === MAIN LOOP ===
bin_id = "67fc17043fdbe7d6eab4d835"

try:
    while True:
        print("📢 Approche ta carte RFID...")
        lcd_display("Approche ta", "carte RFID...")

        current_user_id = "0000"
        quantities = {'plastique': 0, 'verre': 0}

        start = time.time()
        while time.time() - start < 10:
            try:
                id, _ = reader.read_no_block()
                if id:
                    rfid_str = str(id)
                    user_id = check_rfid_in_firestore(rfid_str)
                    if not user_id:
                        print("🚫 Carte inconnue")
                        lcd_display("Carte non", "trouvee !")
                        time.sleep(2)
                        start = time.time()
                    else:
                        current_user_id = user_id
                        print(f"✅ Utilisateur : {user_id}")
                        lcd_display("Utilisateur OK", user_id)
                        break
            except Exception as e:
                print("Erreur RFID :", e)
            time.sleep(0.2)

        if current_user_id == "0000":
            print("⏱️ Temps expiré.")
            lcd_display("Temps expire", "Redemarrage...")
            continue

        print("⚡ Détection activée")
        lcd_display("Detection", "activee...")

        while True:
            try:
                id_check, _ = reader.read_no_block()
                if id_check and check_rfid_in_firestore(str(id_check)) == current_user_id:
                    print("🔐 Fin de session RFID.")
                    lcd_display("Session", "terminee")
                    total = sum(quantities.values())
                    lcd_display("Total:", f"{total} bouteilles")
                    for t, q in quantities.items():
                        if q > 0:
                            send_to_firebase(bin_id, q, t, current_user_id)
                    time.sleep(3)
                    break
            except:
                pass

            distance = detect_distance()
            if distance != -1 and distance < 12:
                print(f"📏 Objet à {distance} cm")
                lcd_display("Objet detecte", f"{distance} cm")
                image = capture_image()
                if image is None:
                    continue

                if not run_detection(image):
                    print("🚫 Pas une bouteille")
                    lcd_display("Pas une", "bouteille")
                    rotate_servo(servo1, 90)
                    time.sleep(0.5)
                    rotate_servo(servo1, 0)
                else:
                    print("✅ Bouteille détectée")
                    lcd_display("Bouteille", "detectee")
                    bottle_type = run_classification(image)
                    print(f"Type : {bottle_type}")
                    lcd_display("Type:", bottle_type)

                    if bottle_type == "plastique":
                        rotate_servo(servo2, 100)
                    else:
                        rotate_servo(servo2, 180)
                    time.sleep(0.5)
                    rotate_servo(servo2, 180)

                    if bottle_type == "plastique":
                        rotate_servo(servo3, 180)
                        time.sleep(0.5)
                        rotate_servo(servo3, 90)
                    else:
                        rotate_servo(servo3, 0)
                        time.sleep(0.5)
                        rotate_servo(servo3, 90)

                    ir_detected = False
                    start_ir = time.time()
                    while time.time() - start_ir < 5:
                        if GPIO.input(IR_PIN) == GPIO.LOW:
                            ir_detected = True
                            break
                        time.sleep(0.1)

                    if ir_detected:
                        quantities[bottle_type] += 1
                        print("👤 Comptabilisé")
                        lcd_display("Bouteille", "comptabilisee")
                    else:
                        print("⚠️ Non detectee IR")
                        lcd_display("Non detectee", "a l'IR")

except KeyboardInterrupt:
    GPIO.cleanup()
    lcd.clear()
    print("\n🛑 Programme arrêté.")
