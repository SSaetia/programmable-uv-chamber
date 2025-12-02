from machine import Pin
import time
import encoderLib

last = 0
e = encoderLib.encoder(10, 11) # Initializes the library with pin CLK on 12 and pin DT on 13

btn = Pin(8, Pin.IN, Pin.PULL_UP)  # usually active LOW

while True:                    # Infinite loop
    value = e.getValue()         # Get rotary encoder value
    if value != last:            # If there is a new value do
        last = value
        print(value)               # In this case it prints the value
    
#     if btn.value() == 0:  # pressed
#         print("Button pressed!")
#         time.sleep(0.1)