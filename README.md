# Game Radio Station

A Raspberry Pi project with a KY-040 rotary encoder, a round SPI LCD, and VLC audio playback. Audio files are stored locally in game/radio folders. Audio output can optionally be routed to a Bluetooth device.

## Hardware

- Raspberry Pi Zero 2 W / Zero 2 WH
- KY-040 rotary encoder
- 1.28-inch SPI LCD, 240 x 240 pixels
- Optional Bluetooth audio device

## Pinout

The software uses BCM GPIO numbering. The tables also include the physical pin numbers of the 40-pin header.

### KY-040

| KY-040 | Raspberry Pi | BCM | Physical pin |
|---|---|---:|---:|
| + | 3.3 V | – | 17 |
| GND | GND | – | 6 |
| CLK / A | GPIO 5 | 5 | 29 |
| DT / B | GPIO 6 | 6 | 31 |
| SW | GPIO 23 | 23 | 16 |

### LCD

| LCD | Raspberry Pi | BCM | Physical pin |
|---|---|---:|---:|
| VCC | 3.3 V | – | 1 |
| GND | GND | – | 9 |
| SDA / MOSI | GPIO 10 | 10 | 19 |
| SCL / SCLK | GPIO 11 | 11 | 23 |
| CS / CE0 | GPIO 8 | 8 | 24 |
| DC | GPIO 25 | 25 | 22 |
| RST | GPIO 27 | 27 | 13 |

The LCD used by this project has no separate BL pin. If your module does have a backlight connection, the driver reserves GPIO 18 (physical pin 12) for it. Do not use GPIO 18 for the KY-040.

Important:

- Power both modules from 3.3 V.
- Raspberry Pi GPIOs are not 5 V tolerant.
- SDA and SCL on this SPI LCD are not I2C lines; they are the MOSI and SCLK signals.
- GPIO 5/6/23 are the encoder pins. GPIO 18 remains reserved for the LCD backlight, or unused when the LCD has no BL pin.

## Controls

- Turn the encoder clockwise: next radio/song
- Turn the encoder counter-clockwise: previous radio/song
- Press the encoder: next game/radio

Each confirmed detent is processed exactly once. GPIO callbacks only enqueue actions; one worker thread processes the actions sequentially. Separate short debounce times are used for the KY-040 rotary encoder and its button.

## Project structure

The complete project is placed directly under `/home/grs`:

~~~text
/home/grs/
├── Startup.py
├── Encoder.py
├── GameRadioStation.py
├── GetRadioData.py
├── PlayRadio.py
├── VLCPlayer.py
├── BluetoothService.py
├── Logger.py
├── Settings.py
├── startup_script.service
├── gameradios/
│   └── Grand Theft Auto/
│       ├── thumbnail.png
│       ├── N-CT FM.mp3
│       └── N-CT FM.png
└── lib/
    ├── LCD_1inch28.py
    ├── config.py
    ├── settings.json
    ├── last_run.json          # generated at runtime
    ├── loading.png
    ├── closed.png
    ├── default_thumbnail.png
    └── logs/
~~~

Each game folder must contain at least one audio file and a `thumbnail.png`. Do not create empty game folders. Song images are searched as `<SongName>.png`; if a song image is missing, the game thumbnail can be used.

Supported audio formats:

- MP3
- WAV

## Step-by-step installation

### 1. Install Raspberry Pi OS

On Windows, install the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

In Raspberry Pi Imager, select:

1. Device: Raspberry Pi Zero 2 W
2. Operating system: Raspberry Pi OS Lite 64-bit
3. Storage: the microSD card
4. Set the Imager presets:
   - Hostname: `GamesRadioStation`
   - Username: `grs`
   - Set a password
   - Configure WLAN
   - Enable SSH
   - Optionally enable USB gadget mode for a direct USB connection

Write the card, eject it safely, and insert it into the Pi.

### 2. Connect over SSH

Wait approximately one minute after the first boot, then connect from PowerShell:

~~~powershell
ssh grs@GamesRadioStation.local
~~~

If `.local` cannot be resolved, use the Pi's IP address:

~~~powershell
ssh grs@<IP-ADDRESS>
~~~

### 3. Update the system

Run on the Pi:

~~~bash
sudo apt update
sudo apt full-upgrade -y
~~~

### 4. Install the required system packages

~~~bash
sudo apt install -y \
  vlc bluez \
  pipewire pipewire-pulse pipewire-audio pipewire-alsa wireplumber \
  libspa-0.2-bluetooth pulseaudio-utils \
  python3-rpi.gpio python3-spidev python3-gpiozero \
  python3-vlc python3-mutagen python3-pydbus \
  python3-pil python3-numpy
~~~

The application uses `pactl` to select the audio output. On current Raspberry Pi OS versions this normally uses PipeWire's PulseAudio compatibility layer; the PulseAudio server itself is not started by the service file.

Enable Bluetooth:

~~~bash
sudo systemctl enable --now bluetooth
~~~

If Bluetooth audio is used, change the target in `/home/grs/lib/settings.json` to a lower-case prefix of the actual device name. For example:

~~~python
"targets": ["n-m405"]
~~~

The target must be lower-case because `BluetoothService` lowercases the discovered device name before comparing it with the target. The service only connects to devices whose reported name starts with the configured prefix.

### Runtime settings

`/home/grs/lib/settings.json` contains the Bluetooth target, the KY-040 pins, the LCD/SPI pins and frequencies, debounce values, and the logging switch. Set `logging.enabled` to `false` to disable both console and file logging. The last selected game and song are stored separately in `/home/grs/lib/last_run.json`.

When upgrading from an older version whose `lib/settings.json` contains only the last selected game and song, `Settings.py` moves that file to `lib/last_run.json` automatically and uses the new configuration defaults.

The default pin configuration is:

~~~json
{
  "encoder": {"clk_pin": 5, "dt_pin": 6, "sw_pin": 23},
  "lcd": {"spi_bus": 0, "spi_device": 0, "rst": 27, "dc": 25, "bl": 18}
}
~~~

### 5. Enable SPI for the LCD

~~~bash
sudo raspi-config
~~~

Select:

~~~text
Interface Options
  → SPI
    → Enable
~~~

Then reboot the Pi:

~~~bash
sudo reboot
~~~

Reconnect over SSH after the reboot.

### 6. Copy the project to `/home/grs`

From PowerShell, in the local project directory:

~~~powershell
scp -r ./* grs@GamesRadioStation:/home/grs/
~~~

Alternatively, copy the complete project content to `/home/grs/` using SFTP/WinSCP.

On the Pi, create the data directory and set the correct ownership:

~~~bash
sudo mkdir -p /home/grs/gameradios
sudo chown -R grs:grs /home/grs
~~~

Create the game folders with their audio files and images below `/home/grs/gameradios/`.

### 7. Set GPIO and audio permissions

~~~bash
sudo usermod -aG gpio,spi,audio,bluetooth grs
id -u grs
sudo loginctl enable-linger grs
sudo reboot
~~~

Log in as `grs` after the reboot. The service file uses `/run/user/1000` as the default runtime directory. If `id -u grs` returns a different number, replace `1000` in `startup_script.service` in the `XDG_RUNTIME_DIR` setting.

### 8. Start PipeWire for user `grs`

Run this command without `sudo`, as user `grs`:

~~~bash
systemctl --user enable --now pipewire pipewire-pulse wireplumber
~~~

Check the audio services:

~~~bash
pactl info
pactl list short sinks
~~~

If `pactl info` works, the audio compatibility layer is reachable. Without a connected Bluetooth device, only a local sink may be listed initially.

### 9. Install the systemd service

The service file is located at `/home/grs/startup_script.service`. It is configured for user `grs` and the project path `/home/grs`.

Install and start it:

~~~bash
sudo install -m 644 /home/grs/startup_script.service \
  /etc/systemd/system/startup_script.service
sudo systemctl daemon-reload
sudo systemctl enable startup_script.service
sudo systemctl start startup_script.service
~~~

Check its status:

~~~bash
sudo systemctl status startup_script.service --no-pager -l
~~~

### 10. Logs and troubleshooting

Service output is written to the systemd journal:

~~~bash
sudo journalctl -u startup_script.service -f
~~~

Useful diagnostics:

~~~bash
sudo journalctl -u startup_script.service -n 100 --no-pager
sudo systemctl status startup_script.service --no-pager -l
~~~

- `203/EXEC` for `/usr/bin/pulseaudio`: an old service file still contains `ExecStartPre=/usr/bin/pulseaudio --start`. Remove that line.
- `209/STDOUT`: an old service file uses a missing `lib/logs_pi` path. The current file uses `StandardOutput=journal` and `StandardError=journal`.
- Only the loading image is visible: check the journal first. Then verify that `/home/grs/gameradios/` exists and every game folder contains an audio file and `thumbnail.png`.
- Bluetooth service is initialized but no target is found: check the device name with `bluetoothctl devices` and use a matching lower-case prefix in `/home/grs/lib/settings.json`. The device must also be powered on and discoverable for the first connection.
- `pactl info` fails: PipeWire/PipeWire-Pulse is not running for user `grs`, or `pulseaudio-utils` is missing.
- The LCD remains blank: enable SPI and verify the pinout in this README.

Reload or restart the service manually:

~~~bash
sudo systemctl daemon-reload
sudo systemctl restart startup_script.service
~~~

## Software architecture

- `Startup.py`: initializes the logger, LCD, Bluetooth, radio controller, and encoder
- `Settings.py`: loads and validates `lib/settings.json`
- `Encoder.py`: handles KY-040 input, debounce, and the serial worker thread
- `GameRadioStation.py`: selects games and songs
- `GetRadioData.py`: scans `/home/grs/gameradios`
- `PlayRadio.py`: handles resume and random-start logic
- `VLCPlayer.py`: controls VLC playback
- `BluetoothService.py`: scans for Bluetooth devices, connects to the target, and selects the audio sink
- `Logger.py`: writes daily logs under `/home/grs/lib/logs`

## Official documentation

- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- [Raspberry Pi OS installation](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Raspberry Pi configuration and audio](https://www.raspberrypi.com/documentation/computers/configuration.html)
- [Raspberry Pi audio options](https://pip-assets.raspberrypi.com/categories/1259-audio-camera-and-display/documents/RP-008124-WP/Choosing%20an%20Audio%20option.pdf)
