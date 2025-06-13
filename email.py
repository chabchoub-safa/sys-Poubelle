import RPi.GPIO as GPIO
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration du capteur HC-SR04
TRIG = 5
ECHO = 6
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

# Fonction pour mesurer la distance
def get_distance():
    GPIO.output(TRIG, False)
    time.sleep(0.1)

    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()
    
    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()
    
    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)

# Fonction d’envoi d’e-mail
def send_email():
    sender_email = "****"
    sender_password = "********"
    receiver_email = "****"

    subject = "Détection d'objet"
    body = "Un objet a été détecté devant la poubelle pendant 30 secondes."

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()
        print("Email envoyé avec succès.")
    except Exception as e:
        print("Erreur lors de l’envoi de l’email:", str(e))

# Programme principal
try:
    detection_start = None
    while True:
        distance = get_distance()
        print(f"Distance : {distance} cm")

        if distance < 15:  # Seuil pour dire qu’il y a un objet
            if detection_start is None:
                detection_start = time.time()
            elif time.time() - detection_start >= 30:  # 30 secondes
                print("Objet détecté pendant 30 secondes. Envoi email.")
                send_email()
                detection_start = None  # Pour éviter les répétitions
                time.sleep(60)  # Attendre avant de vérifier de nouveau
        else:
            detection_start = None  # Réinitialiser si l’objet disparaît

        time.sleep(1)

except KeyboardInterrupt:
    print("Arrêt du programme.")
    GPIO.cleanup()
