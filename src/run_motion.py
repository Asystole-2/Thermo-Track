import os
import time
from dotenv import load_dotenv, find_dotenv
from core.motion.motion_service import MotionService

load_dotenv(find_dotenv())


def main():
    pir_pin = int(os.getenv("PIR_PIN", "11"))
    buzzer_pin = int(os.getenv("BUZZER_PIN", "7"))
    service = MotionService(pir_pin=pir_pin, buzzer_pin=buzzer_pin)
    service.run()


if __name__ == "__main__":
    main()
