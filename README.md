# Game Radio Station (Raspberry Pi Prototype)

## Overview

Game Radio Station is an embedded Python project that turns a Raspberry Pi with a rotary encoder and a round LCD display into a “game-themed radio player”.

It plays audio tracks grouped by “games”, selectable via hardware controls, and outputs audio either locally or via Bluetooth (e.g. car audio systems).

The project was a purely experimental prototype focused on AI-assisted embedded development workflows and system integration on low-power hardware. It was built as a Python-based Raspberry Pi system combining hardware control (rotary encoder, LCD display, Bluetooth audio) with modular software for media playback and device interaction.

Its purpose was to explore how AI tools could support the design and implementation of embedded systems, particularly in managing audio playback, system services, and hardware interfaces under typical Linux-based constraints.

It was not intended as a finished product, but as a technical testbed for AI-driven development in embedded environments.

## Features

- Rotary encoder navigation
  - Rotate: next / previous song
  - Button press: switch game

- Game-based audio system
  - Each folder in `gameradios/` represents a game station
  - Each station contains multiple audio tracks
  - Optional per-song and per-game thumbnails

- Persistent playback state
  - Saves last game and song in JSON
  - Restores state on startup

- Smart playback behavior
  - Random start offset for first play
  - Resume based on elapsed time since last stop

- VLC-based audio engine
  - Uses python-vlc for playback control
  - Repeat and seek support

- Bluetooth audio routing
  - Auto-detect target devices
  - Connect and set PulseAudio sink automatically

- LCD UI
  - 1.28” round display (240x240)
  - Shows loading screen, game art, and song art

- System service integration
  - Runs as systemd service on boot
  - Auto-restarts on failure

## Hardware

- Raspberry Pi (Zero 2 W or similar)
- Rotary Encoder (KY-040 style)
- 1.28" round SPI LCD (240x240)
- Optional Bluetooth audio target

## Software Architecture

### Core Modules

- `Startup.py`
  - Initializes all services and hardware
  - Main runtime entry point

- `GameRadioStation.py`
  - Manages games, songs, state persistence, and UI updates

- `RadioController`
  - Handles playback logic and resume behavior
  - Interfaces with VLC

- `VLCPlayer`
  - Thin wrapper around python-vlc
  - Supports seek, repeat, and event handling

- `Encoder`
  - Handles rotary input and button events
  - Controls navigation logic

- `BluetoothService`
  - Scans and connects to predefined Bluetooth targets
  - Routes audio via PulseAudio

- `Logger`
  - Thread-safe logging system with file rotation

- `GetRadioData`
  - Scans folder structure and builds game/song metadata

## Folder Structure

- gameradios/
  - GameA/
    - track1.mp3
    - track1.png
    - thumbnail.png
- lib/
  - loading.png
  - closed.png
  - default_thumbnail.png
  - logs/

## Installation

### Dependencies

```bash
pip install python-vlc mutagen gpiozero pillow pydbus numpy spidev
sudo apt install vlc pulseaudio bluez
```
Enable service
```bash
sudo nano /etc/systemd/system/startup_script.service
```
Use provided service file, then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now startup_script.service
```

### Behavior Notes
- Audio offset simulation allows “radio-like” continuous playback feel
- Bluetooth sink switching relies on PulseAudio + BlueZ integration
- Encoder input is rate-limited to avoid accidental multiple triggers
- LCD updates block briefly during image transitions

### Limitations
- No real streaming backend (only local files)
- Bluetooth sink detection is device-name dependent
- LCD update pipeline is blocking and not double-buffered
- Code assumes Linux + PulseAudio environment
