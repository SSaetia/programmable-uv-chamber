# UV OVEN controller - MicroPython Version (v2 - Custom Programs)
#
# Adds support for multi-step, multi-loop custom programs
# and saving/loading them to/from flash memory using JSON.
#
# Libraries:
# - encoderLib.encoder  (rotary)
# - picozero (PWM LED, Buzzer, Button)
# - ST7567 (Original Framebuf driver)
# - Lid Safety Switch on GP27
#
# Pins: (Unchanged)
#   Encoder: CLK=GP10, DT=GP11, BTN=GP8
#   LCD(ST7567): SPI1 SCK=GP14, MOSI=GP15,    CS=GP13, A0=GP22, RST=GP20
#   UV PWM: GP26
#   Buzzer: GP17
#   Lid Switch: GP27

from machine import Pin, SPI
import time
from encoderLib import encoder
from picozero import LED, Buzzer, Button
from neopixel import NeoPixel
import json # For saving/loading custom programs
import os   # For checking if programs file exists
from ST7567 import ST7567           # your LCD driver

# ------------------ PIN MAP ------------------
ENC_CLK = 10
ENC_DT  = 11
ENC_BTN_PIN = 8

LCD_SCK = 14
LCD_MOSI= 15
LCD_CS  = 13
LCD_RS  = 22  # A0
LCD_RST = 20

UV_PWM_PIN = 26
BUZZER_PIN = 17

LID_SWITCH_PIN = 27 # Safety lid switch input
NEOPIXEL_PIN = 21   # Data pin for knob/LCD NeoPixels

# ------------------ Color Definitions (Corrected) ------------------
COLOR_NORMAL_1 = (255, 255, 255)
COLOR_NORMAL_2 = (0, 20, 0)
COLOR_NORMAL_3 = (20, 0, 0)

COLOR_ALARM_1 = (0, 255, 0) # Red
COLOR_ALARM_2 = (0, 255, 0) # Red
COLOR_ALARM_3 = (0, 255, 0) # Red

COLOR_OFF = (0, 0, 0)

COLOR_DONE = (255, 0, 0) # Bright Green

# ------------------ Time Unit Definitions ------------------
# (unit_name, default_value, min_val, max_val, step_val)
TIME_UNITS = [
    ("min:sec", 60, 1, 3600),     # Index 0: Value is in seconds
    ("hr:min",  30, 1, 1440),     # Index 1: Value is in minutes
    ("sec:ms", 1000, 100, 60000)  # Index 2: Value is in milliseconds
]
TIME_STEPS = [1, 1, 100] # Encoder step value for each unit

# ------------------ USER LIMITS ------------------
INT_MIN,  INT_MAX  = 0, 100      # %
INT_STEP  = 1                   # % per encoder step
PWM_FREQ  = 1000                # LED PWM frequency (Hz)

# ------------------ Program Storage ------------------
PROGRAMS_FILE = "uv_programs.json"

# ------------------ LCD helper ------------------
def lcd_print(l1, l2=""):
    lcd.fill(0)
    lcd.text(str(l1)[:21], 0, 0, 1)
    lcd.text(str(l2)[:21], 0, 16, 1)
    lcd.show()

def lcd_print_menu(title, item, selected=True):
    """Helper for drawing menu items with a selector."""
    lcd.fill(0)
    lcd.text(str(title)[:21], 0, 0, 1)
    prefix = "> " if selected else "  "
    lcd.text(prefix + str(item)[:19], 0, 16, 1)
    lcd.show()

def fmt_time(value, unit_idx):
    """Formats the 'set_value' based on the selected time unit."""
    try:
        if unit_idx == 0: # min:sec
            m, s = divmod(int(value), 60)
            return f"{m:02d}:{s:02d}"
        elif unit_idx == 1: # hr:min
            h, m = divmod(int(value), 60)
            return f"{h:02d}:{m:02d}"
        elif unit_idx == 2: # sec:ms
            s, ms = divmod(int(value), 1000)
            return f"{s:02d}:{ms:03d}ms"
    except Exception as e:
        print(f"fmt_time error: {e}")
        return "ERR:FMT"

def fmt_time_simple(secs):
    """Always formats a duration in seconds to mm:ss for countdown."""
    m, s = divmod(int(secs), 60)
    return f"{m:02d}:{s:02d}"

# ------------------ Program File Helpers ------------------
def load_programs_from_file():
    """Loads all saved programs from the JSON file into a list."""
    try:
        with open(PROGRAMS_FILE, 'r') as f:
            programs = json.load(f)
            print(f"Loaded {len(programs)} programs.")
            return programs
    except Exception as e:
        print(f"No programs file found or file corrupted: {e}")
        return [] # Return an empty list if file doesn't exist

def save_programs_to_file(programs_list):
    """Saves the entire list of programs to the JSON file."""
    try:
        with open(PROGRAMS_FILE, 'w') as f:
            json.dump(programs_list, f)
            print(f"Saved {len(programs_list)} programs.")
    except Exception as e:
        print(f"Error saving programs: {e}")

def get_duration_sec(step):
    """Calculates runtime in seconds from a program step dict."""
    idx = step["u"] # unit_idx
    val = step["v"] # value
    if idx == 0: return val
    if idx == 1: return val * 60
    if idx == 2: return val / 1000.0
    return 0

# ------------------ INIT HARDWARE ------------------
spi = SPI(1, baudrate=5_000_000, polarity=1, phase=1, sck=Pin(LCD_SCK), mosi=Pin(LCD_MOSI))
lcd = ST7567(spi, a0=Pin(LCD_RS), cs=Pin(LCD_CS), rst=Pin(LCD_RST),
             elecvolt=0x2F, regratio=0x03, invX=False, invY=True, invdisp=False)
enc = encoder(ENC_CLK, ENC_DT)
btn = Button(ENC_BTN_PIN, pull_up=True)
uv = LED(UV_PWM_PIN, pwm=True)
bz = Buzzer(BUZZER_PIN)
lid_switch = Pin(LID_SWITCH_PIN, Pin.IN, Pin.PULL_DOWN)

try:
    neopixel = NeoPixel(Pin(NEOPIXEL_PIN), 3)
    # ... (set initial colors) ...
except Exception as e:
    neopixel = None
# (NeoPixel init code identical to previous version)
# ... [omitted for brevity, assume it's the same] ...

# ------------------ STATE MACHINE DEFINITIONS ------------------

# Main operating mode
# *** FIX 1: Added MODE_CUSTOM_CREATE ***
MODE_MAIN_MENU, MODE_SIMPLE, MODE_CUSTOM_MENU, MODE_CUSTOM_CREATE = 0, 1, 2, 3
main_state = MODE_MAIN_MENU

main_menu_items = ["Simple Mode", "Custom Mode"]
main_menu_idx = 0

# State machine for "Simple Mode"
S_IDLE, S_SET_TIME_UNIT, S_SET_TIME, S_SET_INTENS, S_RUNNING, S_DONE = 0, 1, 2, 3, 4, 5
simple_state = S_IDLE

# State machine for "Custom Mode Menu"
# Note: "Save" is part of the "Create" process
C_MENU_LOAD, C_MENU_CREATE, C_MENU_RUN = 0, 1, 2
custom_menu_items = ["Load Program", "Create New", "Run Program"]
custom_menu_idx = 0

# State machine for "Custom Program Creation"
C_CREATE_START, C_CREATE_SET_TIME_UNIT, C_CREATE_SET_TIME, C_CREATE_SET_INTENS, C_CREATE_ADD_STEP, C_CREATE_SET_LOOPS, C_CREATE_SET_NAME, C_CREATE_SAVE_PROG = 0, 1, 2, 3, 4, 5, 6, 7
create_state = C_CREATE_START

# State machine for "Custom Program Runner"
C_RUN_START, C_RUN_STEP, C_RUN_DONE = 0, 1, 2
run_state = C_RUN_START

# State machine for "Load Program"
C_LOAD_SELECT, C_LOAD_CONFIRM = 0, 1
load_state = C_LOAD_SELECT # Use -1 to indicate "not in load state"
load_program_idx = 0

# ------------------ Global Variables ------------------
_last_enc = enc.getValue()

# --- For Simple Mode ---
s_current_time_unit_idx = 0
s_set_value = TIME_UNITS[0][1]
s_set_int  = 50
s_run_duration_sec = 0.0
s_start_ts = None

# --- For Custom Mode ---
saved_programs = [] # List of all programs from file
current_program = {} # The program being created or selected to run
temp_step = {} # A dict for the step being created
temp_program_name = "P-01"
temp_program_loops = 1

c_run_duration_sec = 0.0
c_start_ts = None
c_run_current_step = 0
c_run_current_loop = 1

# *** FIX 2: Added temp_add_another variable ***
temp_add_another = True # For C_CREATE_ADD_STEP toggle

# --- For NeoPixel Blinker ---
last_blink_ms = time.ticks_ms()
blink_interval_ms = 500
blink_state_on = True
lid_was_open = False # (from previous code)

def read_delta():
    global _last_enc
    v = enc.getValue()
    d = v - _last_enc
    if d != 0:
        _last_enc = v
    return d

def beep(ms=120):
    bz.on()
    time.sleep_ms(ms)
    bz.off()

# ------------------ MAIN LOOP ------------------
lcd.fill(0)  
lcd.text("Loading...", 10, 10, 1)  
lcd.show()

saved_programs = load_programs_from_file()
time.sleep(1)

# Check lid before starting
if lid_switch.value() == 0: # 0 = Lid is Open
    lcd_print("!! CLOSE LID !!", "To begin")
    if neopixel:
        neopixel[0] = COLOR_ALARM_1; neopixel[1] = COLOR_ALARM_1; neopixel[2] = COLOR_ALARM_1
        neopixel.write()
    lid_was_open = True
else:
    lcd_print_menu("Main Menu", main_menu_items[main_menu_idx]) # Start at main menu
    lid_was_open = False

# Initialize neopixels to normal if lid is closed
if not lid_was_open and neopixel:
    neopixel[0] = COLOR_NORMAL_1; neopixel[1] = COLOR_NORMAL_2; neopixel[2] = COLOR_NORMAL_3
    neopixel.write()

# --- Super Loop ---
while True:
    d = read_delta()
    now = time.ticks_ms()
    is_lid_open = (lid_switch.value() == 0)
    
    # --- 1. Global NeoPixel & Safety Management ---
    
    # Check for emergency stop on lid open
    if is_lid_open:
        if (main_state == MODE_SIMPLE and simple_state == S_RUNNING) or \
           (main_state == MODE_CUSTOM_MENU and c_start_ts is not None): # Simplified check
            
            uv.off() # Stop UV immediately!
            main_state = MODE_MAIN_MENU # Return to main menu
            simple_state = S_IDLE
            c_start_ts = None # Stop custom run
            
            beep(200); time.sleep_ms(100); beep(200)
            lcd_print("!! LID OPENED !!", "RUN CANCELED")
            time.sleep_ms(1500)
            # The loop will now be in IDLE/MENU and show "CLOSE LID"
            continue

    # Handle NeoPixel blinking
    # Note: RUNNING states don't blink, they are solid
    if simple_state == S_DONE or run_state == C_RUN_DONE:
        # --- Green Blink (Job Finished) ---
        if neopixel and time.ticks_diff(now, last_blink_ms) > blink_interval_ms:
            last_blink_ms = now; blink_state_on = not blink_state_on
            color = COLOR_DONE if blink_state_on else COLOR_OFF
            neopixel[0] = color; neopixel[1] = color; neopixel[2] = color
            neopixel.write()
            
    elif is_lid_open:
        # --- Red Blink (Lid Open Alarm) ---
        if neopixel and time.ticks_diff(now, last_blink_ms) > blink_interval_ms:
            last_blink_ms = now; blink_state_on = not blink_state_on
            color = COLOR_ALARM_1 if blink_state_on else COLOR_OFF
            neopixel[0] = color; neopixel[1] = color; neopixel[2] = color
            neopixel.write()
        lid_was_open = True
        
    elif not is_lid_open and lid_was_open:
        # --- Lid just closed: Restore normal colors ---
        if neopixel:
            neopixel[0] = COLOR_NORMAL_1; neopixel[1] = COLOR_NORMAL_2; neopixel[2] = COLOR_NORMAL_3
            neopixel.write()
        lid_was_open = False
        
    # --- 2. State Machine Logic ---

    # --- MAIN MENU ---
    if main_state == MODE_MAIN_MENU:
        # --- (Logic ใหม่) หมุนเพื่อเปลี่ยนตัวเลือก ---
        if d != 0:
            main_menu_idx = (main_menu_idx + 1) % 2 # สลับค่า 0 -> 1 -> 0
            lcd_print_menu("Main Menu", main_menu_items[main_menu_idx])
            
        # --- (Logic ใหม่) กดเพื่อยืนยันการเข้าโหมด ---
        if btn.is_pressed:
            time.sleep_ms(180)
            if is_lid_open:
                beep(100); lcd_print("!! CLOSE LID !!", "")
            else:
                beep(60)
                
                # ตรวจสอบว่าเลือกอะไรไว้ แล้วค่อยเปลี่ยน 'main_state'
                if main_menu_idx == 0: # 0 = Simple Mode
                    main_state = MODE_SIMPLE
                    simple_state = S_IDLE
                    lcd_print("Simple Mode", "Press to set")
                    
                elif main_menu_idx == 1: # 1 = Custom Mode
                    main_state = MODE_CUSTOM_MENU
                    custom_menu_idx = 0
                    lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
    
    # --- SIMPLE MODE ---
    elif main_state == MODE_SIMPLE:
        # This block is the *entire* state machine from the previous file
        # All "state" variables are renamed to "simple_state"
        
        if simple_state == S_IDLE:
            if btn.is_pressed:
                time.sleep_ms(180)
                if is_lid_open:
                    beep(100); lcd_print("!! CLOSE LID !!", "Press to set")
                else:
                    simple_state = S_SET_TIME_UNIT
                    unit_name = TIME_UNITS[s_current_time_unit_idx][0]
                    lcd_print("Set Time Unit", unit_name)
                    beep(60)

        elif simple_state == S_SET_TIME_UNIT:
            if d != 0:
                s_current_time_unit_idx = (s_current_time_unit_idx + (1 if d > 0 else -1)) % len(TIME_UNITS)
                unit_name = TIME_UNITS[s_current_time_unit_idx][0]
                lcd_print("Set Time Unit", unit_name)
                s_set_value = TIME_UNITS[s_current_time_unit_idx][1]
            if btn.is_pressed:
                time.sleep_ms(180); beep(60)
                simple_state = S_SET_TIME
                lcd_print("Set Time", fmt_time(s_set_value, s_current_time_unit_idx))

        elif simple_state == S_SET_TIME:
            if d != 0:
                unit_idx = s_current_time_unit_idx
                step = TIME_STEPS[unit_idx]
                min_val = TIME_UNITS[unit_idx][2]
                max_val = TIME_UNITS[unit_idx][3]
                s_set_value = max(min_val, min(max_val, s_set_value + step * (1 if d > 0 else -1)))
                lcd_print("Set Time", fmt_time(s_set_value, unit_idx))
            if btn.is_pressed:
                time.sleep_ms(180); beep(60)
                simple_state = S_SET_INTENS
                lcd_print("Set Intensity", f"{s_set_int:3d}%")

        elif simple_state == S_SET_INTENS:
            if d != 0:
                s_set_int = max(INT_MIN, min(INT_MAX, s_set_int + INT_STEP*(1 if d>0 else -1)))
                lcd_print("Set Intensity", f"{s_set_int:3d}%")
            if btn.is_pressed:
                time.sleep_ms(180)
                if is_lid_open:
                    beep(150); lcd_print("!! CLOSE LID !!", "Press to retry")
                else:
                    idx = s_current_time_unit_idx
                    if idx == 0: s_run_duration_sec = s_set_value
                    elif idx == 1: s_run_duration_sec = s_set_value * 60
                    elif idx == 2: s_run_duration_sec = s_set_value / 1000.0
                    
                    uv.value = s_set_int/100.0
                    s_start_ts = time.ticks_ms()
                    simple_state = S_RUNNING
                    lcd_print("RUN", f"{fmt_time_simple(s_run_duration_sec)} @ {s_set_int}%")
                    beep(120)

        elif simple_state == S_RUNNING:
            elapsed_sec = time.ticks_diff(now, s_start_ts) / 1000.0
            remain_sec = max(0, s_run_duration_sec - elapsed_sec)
            lcd_print("RUN", f"{fmt_time_simple(remain_sec)} @ {s_set_int}%")
            
            if btn.is_pressed: # Long press cancel
                t0 = time.ticks_ms()
                while btn.is_pressed and time.ticks_diff(time.ticks_ms(), t0) < 600: time.sleep_ms(10)
                if btn.is_pressed:
                    uv.off(); s_start_ts = None
                    simple_state = S_IDLE
                    main_state = MODE_MAIN_MENU # Go back to main menu
                    lcd_print("Canceled", "Main Menu")
                    beep(100); time.sleep_ms(300)
                    
            if remain_sec <= 0:
                uv.off(); s_start_ts = None
                for _ in range(3): beep(120); time.sleep_ms(120)
                simple_state = S_DONE
                lcd_print("DONE", "Press->Menu")
                last_blink_ms = now; blink_state_on = True

        elif simple_state == S_DONE:
            if btn.is_pressed:
                time.sleep_ms(180)
                simple_state = S_IDLE
                main_state = MODE_MAIN_MENU # Go back to main menu
                lcd_print_menu("Main Menu", main_menu_items[main_menu_idx]) # Use main menu index
                lid_was_open = True # Force neopixel update

    # --- CUSTOM MODE MENU ---
    elif main_state == MODE_CUSTOM_MENU:
        
        # --- CUSTOM RUN Sub-State (must be checked first) ---
        if c_start_ts is not None: # Check if running, not by menu index
            # We are currently running a custom program
            
            # (Safety check for lid open is at the top of the loop)
            
            elapsed_sec = time.ticks_diff(now, c_start_ts) / 1000.0
            remain_sec = max(0, c_run_duration_sec - elapsed_sec)
            
            step = current_program["steps"][c_run_current_step]
            step_int = step["i"]
            lcd_print(f"L{c_run_current_loop}/{current_program['loops']} S{c_run_current_step+1}/{len(current_program['steps'])} @{step_int}%",
                      f"Time: {fmt_time_simple(remain_sec)}")

            if btn.is_pressed: # Long press cancel
                t0 = time.ticks_ms()
                while btn.is_pressed and time.ticks_diff(time.ticks_ms(), t0) < 600: time.sleep_ms(10)
                if btn.is_pressed:
                    uv.off(); c_start_ts = None
                    main_state = MODE_MAIN_MENU # Go back to main menu
                    lcd_print("Canceled", "Main Menu")
                    beep(100); time.sleep_ms(300)

            if remain_sec <= 0:
                # Step is done, move to next step or loop
                c_run_current_step += 1
                if c_run_current_step >= len(current_program["steps"]):
                    # End of steps, move to next loop
                    c_run_current_step = 0
                    c_run_current_loop += 1
                    if c_run_current_loop > current_program["loops"]:
                        # --- Program Finished ---
                        uv.off(); c_start_ts = None
                        for _ in range(3): beep(120); time.sleep_ms(120)
                        run_state = C_RUN_DONE # Use this to trigger blink
                        lcd_print("DONE", "Press->Menu")
                        last_blink_ms = now; blink_state_on = True
                    else:
                        # Start next loop (run next step)
                        new_step = current_program["steps"][c_run_current_step]
                        uv.value = new_step["i"] / 100.0
                        c_run_duration_sec = get_duration_sec(new_step)
                        c_start_ts = time.ticks_ms()
                else:
                    # Start next step
                    new_step = current_program["steps"][c_run_current_step]
                    uv.value = new_step["i"] / 100.0
                    c_run_duration_sec = get_duration_sec(new_step)
                    c_start_ts = time.ticks_ms()
            
        # --- CUSTOM DONE Sub-State ---
        elif run_state == C_RUN_DONE:
            if btn.is_pressed:
                time.sleep_ms(180)
                run_state = C_RUN_START # Reset runner
                main_state = MODE_MAIN_MENU # Go back to main menu
                lcd_print_menu("Main Menu", main_menu_items[main_menu_idx]) # Use main menu index
                lid_was_open = True
        
        # *** FIX 3: Replaced CUSTOM MENU Navigation logic ***
        # --- CUSTOM MENU Navigation ---
        elif load_state == -1: # Only navigate if NOT in load state
            if d != 0:
                custom_menu_idx = (custom_menu_idx + (1 if d > 0 else -1)) % len(custom_menu_items)
                lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
            
            if btn.is_pressed:
                time.sleep_ms(180) # Debounce
                t0 = time.ticks_ms()
                is_long = False
                while btn.is_pressed:
                    if time.ticks_diff(time.ticks_ms(), t0) > 600:
                        is_long = True
                        break
                
                if is_long:
                    # --- LONG PRESS: Go Back to Main Menu ---
                    beep(100)
                    main_state = MODE_MAIN_MENU
                    lcd_print_menu("Main Menu", main_menu_items[main_menu_idx])
                    while btn.is_pressed: time.sleep_ms(10) # Wait for release
                
                else:
                    # --- SHORT PRESS: Confirm Selection ---
                    if is_lid_open:
                        beep(100); lcd_print("!! CLOSE LID !!", "")
                        continue

                    if custom_menu_idx == C_MENU_LOAD:
                        # --- Go to LOAD Program State ---
                        load_state = C_LOAD_SELECT
                        load_program_idx = 0
                        if not saved_programs:
                            lcd_print("Load Program", "No Programs!")
                            time.sleep_ms(1000)
                            load_state = -1 # Exit load state
                            lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
                        else:
                            lcd_print_menu(f"Load? ({load_program_idx+1}/{len(saved_programs)})", saved_programs[load_program_idx]["name"])

                    elif custom_menu_idx == C_MENU_CREATE:
                        # --- Go to CREATE Program State ---
                        main_state = MODE_CUSTOM_CREATE
                        create_state = C_CREATE_START
                        current_program = {"name": "New", "loops": 1, "steps": []} # Reset program
                        temp_step = {}
                        lcd_print("Create Program", "Add Step 1?")

                    elif custom_menu_idx == C_MENU_RUN:
                        # --- Go to RUN Program State ---
                        if not current_program or not current_program.get("steps"):
                            lcd_print("Run Program", "No PGM Loaded!")
                            time.sleep_ms(1000)
                            lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
                        else:
                            beep(120)
                            run_state = C_RUN_START
                            c_run_current_step = 0
                            c_run_current_loop = 1
                            
                            step = current_program["steps"][0]
                            uv.value = step["i"] / 100.0
                            c_run_duration_sec = get_duration_sec(step)
                            c_start_ts = time.ticks_ms()
        
        # *** FIX 4: Replaced LOAD Program Sub-State logic ***
        # --- Handle LOAD Program Sub-State ---
        if load_state != -1: # -1 means not in load state
            if load_state == C_LOAD_SELECT:
                if d != 0 and saved_programs:
                    load_program_idx = (load_program_idx + (1 if d > 0 else -1)) % len(saved_programs)
                    lcd_print_menu(f"Load? ({load_program_idx+1}/{len(saved_programs)})", saved_programs[load_program_idx]["name"])
                
                if btn.is_pressed:
                    time.sleep_ms(180) # Debounce
                    t0 = time.ticks_ms()
                    is_long = False
                    while btn.is_pressed:
                        if time.ticks_diff(time.ticks_ms(), t0) > 600:
                            is_long = True
                            break
                    
                    if is_long:
                        # --- LONG PRESS: Go Back to Custom Menu ---
                        beep(100)
                        load_state = -1 # Exit load state
                        lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
                        while btn.is_pressed: time.sleep_ms(10) # Wait for release
                    
                    else:
                        # --- SHORT PRESS: Confirm Load ---
                        if saved_programs:
                            beep(60)
                            current_program = saved_programs[load_program_idx]
                            load_state = -1 # Exit load state
                            lcd_print(f"Loaded:", current_program['name'])
                            time.sleep_ms(1000)
                            lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
            
    # *** FIX 5: Replaced CUSTOM CREATE MODE logic ***
    # --- CUSTOM CREATE MODE ---
    elif main_state == MODE_CUSTOM_CREATE:
        
        # --- Handle Button Press (Short vs Long) ---
        if btn.is_pressed:
            time.sleep_ms(180) # Debounce
            t0 = time.ticks_ms()
            is_long = False
            while btn.is_pressed:
                if time.ticks_diff(time.ticks_ms(), t0) > 600:
                    is_long = True
                    break
            
            if is_long:
                # --- LONG PRESS (GLOBAL): Cancel creation, go back to Custom Menu ---
                beep(100)
                main_state = MODE_CUSTOM_MENU
                create_state = C_CREATE_START # Reset create state
                lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
                while btn.is_pressed: time.sleep_ms(10) # Wait for release
                continue 
            
            else:
                # --- SHORT PRESS: Handle confirmation for the *current* state ---
                beep(60) # All short presses beep
                
                if create_state == C_CREATE_START:
                    create_state = C_CREATE_SET_TIME_UNIT
                    s_current_time_unit_idx = 0; s_set_value = TIME_UNITS[0][1]; unit_name = TIME_UNITS[0][0]
                    lcd_print(f"Step {len(current_program['steps'])+1}: Time Unit", unit_name)
                
                elif create_state == C_CREATE_SET_TIME_UNIT:
                    create_state = C_CREATE_SET_TIME
                    temp_step = {"u": s_current_time_unit_idx, "v": s_set_value}
                    lcd_print(f"Step {len(current_program['steps'])+1}: Set Time", fmt_time(s_set_value, s_current_time_unit_idx))
                
                elif create_state == C_CREATE_SET_TIME:
                    temp_step["v"] = s_set_value
                    create_state = C_CREATE_SET_INTENS
                    s_set_int = 50
                    lcd_print(f"Step {len(current_program['steps'])+1}: Intensity", f"{s_set_int:3d}%")
                
                elif create_state == C_CREATE_SET_INTENS:
                    temp_step["i"] = s_set_int
                    current_program["steps"].append(temp_step)
                    create_state = C_CREATE_ADD_STEP
                    temp_add_another = True # Reset toggle
                    lcd_print_menu(f"Step {len(current_program['steps'])} Added!", "Add Another?")
                
                elif create_state == C_CREATE_ADD_STEP:
                    if temp_add_another: # "Yes" was selected
                        create_state = C_CREATE_SET_TIME_UNIT # Loop back
                        s_current_time_unit_idx = 0
                        s_set_value = TIME_UNITS[s_current_time_unit_idx][1]
                        unit_name = TIME_UNITS[s_current_time_unit_idx][0]
                        lcd_print(f"Step {len(current_program['steps'])+1}: Time Unit", unit_name)
                    else: # "No" was selected
                        create_state = C_CREATE_SET_LOOPS
                        temp_program_loops = 1
                        lcd_print("Set Total Loops", f"{temp_program_loops}x")
                
                elif create_state == C_CREATE_SET_LOOPS:
                    current_program["loops"] = temp_program_loops
                    create_state = C_CREATE_SET_NAME
                    p_num = 1; p_names = [p["name"] for p in saved_programs]
                    while f"P-{p_num:02d}" in p_names: p_num += 1
                    temp_program_name = f"P-{p_num:02d}"
                    lcd_print("Set Name", temp_program_name)
                
                elif create_state == C_CREATE_SET_NAME:
                    current_program["name"] = temp_program_name
                    create_state = C_CREATE_SAVE_PROG
                    lcd_print("Save Program?", current_program["name"])
                
                elif create_state == C_CREATE_SAVE_PROG:
                    # (User's original save logic)
                    found_idx = -1
                    for i, p in enumerate(saved_programs):
                        if p["name"] == current_program["name"]:
                            found_idx = i; break
                    if found_idx != -1: saved_programs[found_idx] = current_program
                    else: saved_programs.append(current_program)
                    save_programs_to_file(saved_programs)
                    
                    lcd_print("Program Saved!", "")
                    time.sleep_ms(1000)
                    main_state = MODE_CUSTOM_MENU
                    custom_menu_idx = 0
                    lcd_print_menu("Custom Menu", custom_menu_items[custom_menu_idx])
        
        # --- Handle Encoder Rotations (d != 0) ---
        elif d != 0:
            if create_state == C_CREATE_SET_TIME_UNIT:
                s_current_time_unit_idx = (s_current_time_unit_idx + (1 if d > 0 else -1)) % len(TIME_UNITS)
                unit_name = TIME_UNITS[s_current_time_unit_idx][0]
                lcd_print(f"Step {len(current_program['steps'])+1}: Time Unit", unit_name)
                s_set_value = TIME_UNITS[s_current_time_unit_idx][1]
            
            elif create_state == C_CREATE_SET_TIME:
                unit_idx = temp_step["u"]; step = TIME_STEPS[unit_idx]
                min_val = TIME_UNITS[unit_idx][2]; max_val = TIME_UNITS[unit_idx][3]
                s_set_value = max(min_val, min(max_val, s_set_value + step * (1 if d > 0 else -1)))
                lcd_print(f"Step {len(current_program['steps'])+1}: Set Time", fmt_time(s_set_value, unit_idx))
            
            elif create_state == C_CREATE_SET_INTENS:
                s_set_int = max(INT_MIN, min(INT_MAX, s_set_int + INT_STEP*(1 if d>0 else -1)))
                lcd_print(f"Step {len(current_program['steps'])+1}: Intensity", f"{s_set_int:3d}%")
            
            elif create_state == C_CREATE_ADD_STEP:
                temp_add_another = not temp_add_another
                lcd_print_menu(f"Step {len(current_program['steps'])} Added!", "Add Another?" if temp_add_another else "Finish?")
            
            elif create_state == C_CREATE_SET_LOOPS:
                temp_program_loops = max(1, min(99, temp_program_loops + (1 if d > 0 else -1)))
                lcd_print("Set Total Loops", f"{temp_program_loops}x")
            
            elif create_state == C_CREATE_SET_NAME:
                try:
                    p_num = int(temp_program_name.split('-')[1])
                except:
                    p_num = 1 # Failsafe
                p_num = max(1, min(99, p_num + (1 if d > 0 else -1)))
                temp_program_name = f"P-{p_num:02d}"
                lcd_print("Set Name", temp_program_name)


    time.sleep_ms(30)