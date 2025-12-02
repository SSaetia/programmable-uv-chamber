# Programmable Photopolymerization Chamber
### Irradiance Profiling for Stress-Free Curing

## 🚧 Safety Notice

This system involves high-intensity UV radiation (405nm). Always wear appropriate UV-blocking eyewear during operation. Ensure the enclosure is light-tight before activation. This project is intended strictly for experimental and educational use; users are responsible for ensuring safe operation in their own implementations.

## 📌 Project Overview

This project involves the development of a high-precision, programmable UV photopolymerization chamber designed to address the limitations of conventional fixed-irradiance curing systems. By integrating a microcontroller-based regulation system (Raspberry Pi Pico), this instrument enables dynamic irradiance profiling (e.g., ramp, step, and pulse modes). This capability is critical for controlling polymerization kinetics, thereby mitigating exothermic spikes and shrinkage stress, which are the primary causes of voids and micro-cracks in sensitive photopolymer resins.

## ⚙️ System Description

This chamber provides precise **Pulse Width Modulation (PWM)** control over 405nm UV irradiance and high-resolution timing (hr:min:sec:ms). The system operates in two primary modes:

1.  **Standard Mode:** Constant intensity curing for general applications.
2.  **Custom Mode:** Allows for programmable irradiance profiling. Users can define specific loops, intensity gradients, and duration for advanced curing protocols.

**Safety Interlock System:**
The chamber is equipped with a hardware-level safety check. The **Visual Status Indicator** (knob LED and display) provides real-time operational feedback:
* **Blinking Red:** Safety interlock open (door not secure). UV emission is disabled.
* **Green:** System secure and ready for operation.

The firmware includes a library structure that allows for the development of specific curing algorithms and custom profile generation.

## ✅ Key Features

* **Precise Irradiance Control:** Fine-tuned PWM regulation for 405nm UV LEDs.
* **High-Resolution Timing:** Adjustable down to millisecond intervals for exact exposure.
* **Integrated Safety Interlock:** Automatic cutoff and visual warning system to prevent accidental UV exposure.
* **Programmable Cycling:** Customizable loop setup for ramp, step, and pulse curing profiles.

## 🔌 Wiring Diagram

![Wiring Diagram](docs/wiring_diagram.png)
*(Note: Upload your wiring diagram image to a 'docs' folder and verify the path)*

## 📂 Repository Structure

* `/lib` Libraries
* `/example` Programming examples
* `/photos` Assembly and prototype images

## 🛠️ Hardware

* **Controller:** MKS Mini 12864 V3
* **MCU Interface:** Raspberry Pi Pico (Pi interface)
* **Sensors:** Limit switch (Door Safety)
* **Actuators:** 405nm UV LED Array

## 🧪 Applications

* Post-curing of SLA/DLP 3D printed parts
* Material science research (polymerization stress testing)
* Sterilization and cleaning protocols

## 📖 License

This project is provided for research and educational purposes only.
