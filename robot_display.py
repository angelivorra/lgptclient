import os
import time

# Hide cursor
os.system("printf '\033[?25l'")

try:
    # Your code to display images on the robot screen
    print("Displaying images...")
    # Example: keep running for some time
    time.sleep(10)
    print("Image display finished.")

finally:
    # Show cursor again when the script ends or is interrupted
    os.system("printf '\033[?25h'")
    print("Cursor restored.")

