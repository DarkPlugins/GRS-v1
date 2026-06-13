import threading
import time
import os

from pydbus import SystemBus
import subprocess

class BluetoothService:
    def __init__(self, logger, root_path: str, targets, scan_interval: int = 5, auto_start: bool = True):
        self.logger = logger
        self.root_path = os.path.abspath(root_path)
        self.scan_interval = scan_interval
        self._running = False
        self._thread = None
        self._connected_mac = None
        self.targets = targets  # list of device name prefixes (lowercase)
        self.logger.write(f"[INFO] BluetoothService started with targets: {self.targets}")

        # D-Bus Setup
        try:
            self.bus = SystemBus()
            self.adapter_path = "/org/bluez/hci0"
            self.adapter = self.bus.get("org.bluez", self.adapter_path)
        except Exception as e:
            self.logger.write(f"[WARN] BlueZ/D-Bus init failed: {e}")
            self.bus = None
            self.adapter = None

        if auto_start:
            self.start()


    # --- existing auto-connection loop left mostly unchanged, using self.targets ---
    def _scan_loop(self):
        if not self.adapter:
            self.logger.write("[WARN] No BlueZ Adapter, Scan Loop ended.")
            return
        self._running = True
        while self._running and not self._connected_mac:
            try:
                props = self.adapter.GetAll("org.bluez.Adapter1")
                discovering = props.get("Discovering", False)
                if not discovering:
                    self.adapter.StartDiscovery()

                time.sleep(3)

                managed_objects = self.bus.get("org.bluez", "/").GetManagedObjects()
                for path, props in managed_objects.items():
                    dev = props.get("org.bluez.Device1")
                    if not dev:
                        continue
                    name = dev.get("Name", "").lower()
                    mac = dev.get("Address")
                    if any(name.startswith(t) for t in self.targets):
                        self.logger.write(f"[INFO] Found target: {dev.get('Name')} ({mac})")
                        if not dev.get("Connected", False):
                            device = self.bus.get("org.bluez", path)
                            try:
                                device.Connect()
                                self._connected_mac = mac
                                self.logger.write(f"Connected with {dev.get('Name')} ({mac})")
                                self._set_pulseaudio_sink(mac)
                                self.adapter.StopDiscovery()
                                return
                            except Exception as e:
                                self.logger.write(f"Connection to {mac} failed: {e}")

                if discovering:
                    self.adapter.StopDiscovery()

            except Exception as e:
                self.logger.write(f"[WARN] Scan Loop Exception: {e}")

            wait = 0
            while wait < self.scan_interval and self._running and not self._connected_mac:
                time.sleep(1)
                wait += 1

    def _set_pulseaudio_sink(self, mac):
        self.logger.write(f"Waiting on PulseAudio-Sink for {mac} ...")
        target_fragment = mac.replace(":", "_").lower()
        for _ in range(20):
            sinks = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True)
            for line in sinks.stdout.splitlines():
                if target_fragment in line.lower():
                    sink_name = line.split("\t")[1]
                    self.logger.write(f"PulseAudio-Sink found: {sink_name}, set as default")
                    subprocess.run(["pactl", "set-default-sink", sink_name])
                    move_cmd = f"pactl list short sink-inputs | awk '{{print $1}}' | xargs -r -I{{}} pactl move-sink-input {{}} {sink_name}"
                    subprocess.run(["bash", "-lc", move_cmd])
                    self.logger.write("Audio successfully transferred to Bluetooth-Device.")
                    return
            time.sleep(1)
        self.logger.write(f"[WARN] PulseAudio-Sink for {mac} not found.")

    def start(self):
        if self._thread and self._thread.is_alive():
            self.logger.write("[WARN] BluetoothService already running.")
            return
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        self.logger.write("[INFO] BluetoothService-Thread started.")

    def stop(self):
        self.logger.write("[INFO] Stopping BluetoothService...")
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._connected_mac:
            try:
                device = self.bus.get("org.bluez", f"/org/bluez/hci0/dev_{self._connected_mac.replace(':','_')}")
                device.Disconnect()
                self.logger.write(f"Disconnected from {self._connected_mac}")
            except Exception:
                pass
        self.logger.write("[INFO] BluetoothService stopped.")

    def disconnect_all_targets(self):
        """
        Trennt alle aktuell verbundenen Bluetooth-Geräte,
        ohne den Scan-Thread oder Service zu stoppen.
        """
        if not self.bus:
            self.logger.write("[WARN] No D-Bus available, cannot disconnect any device.")
            return

        try:
            managed_objects = self.bus.get("org.bluez", "/").GetManagedObjects()
            disconnected = 0

            for path, props in managed_objects.items():
                dev = props.get("org.bluez.Device1")
                if not dev:
                    continue

                name = dev.get("Name", "Unbekannt")
                mac = dev.get("Address")
                connected = dev.get("Connected", False)

                # Only disconnect when connected
                if connected:
                    try:
                        device = self.bus.get("org.bluez", path)
                        device.Disconnect()
                        disconnected += 1
                        self.logger.write(f"[INFO] Disconnected from {name} ({mac})")
                    except Exception as e:
                        self.logger.write(f"[WARN] Disconnecting from {name} ({mac}) failed: {e}")

            if disconnected == 0:
                self.logger.write("[INFO] No connected devices found.")
            else:
                self.logger.write(f"[INFO] {disconnected} Device(s) disconnected.")

            # Reset internal state
            self._connected_mac = None

        except Exception as e:
            self.logger.write(f"[WARN] Error while disconnecting all targets: {e}")
