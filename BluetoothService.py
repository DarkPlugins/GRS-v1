import os
import subprocess
import threading

from pydbus import SystemBus


class BluetoothService:
    def __init__(
        self,
        logger,
        root_path: str,
        targets,
        scan_interval: int = 5,
        auto_start: bool = True,
    ):
        self.logger = logger
        self.root_path = os.path.abspath(root_path)
        self.scan_interval = max(1, int(scan_interval))
        self._running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._connected_mac = None
        self.targets = tuple(str(target).lower() for target in targets)
        self.logger.write(f"[INFO] BluetoothService started with targets: {self.targets}")

        try:
            self.bus = SystemBus()
            self.adapter_path = "/org/bluez/hci0"
            self.adapter = self.bus.get("org.bluez", self.adapter_path)
        except Exception as exc:
            self.logger.write(f"[WARN] BlueZ/D-Bus init failed: {exc}")
            self.bus = None
            self.adapter = None

        if auto_start:
            self.start()

    def _is_target(self, name: str) -> bool:
        return any(name.lower().startswith(target) for target in self.targets)

    def _scan_loop(self):
        if not self.adapter or not self.bus:
            self.logger.write("[WARN] No BlueZ Adapter, scan loop ended.")
            self._running = False
            return

        self._running = True
        while self._running and not self._stop_event.is_set():
            discovery_started = False
            try:
                adapter_props = self.adapter.GetAll("org.bluez.Adapter1")
                if not adapter_props.get("Discovering", False):
                    self.adapter.StartDiscovery()
                    discovery_started = True

                if self._stop_event.wait(3):
                    break

                managed_objects = self.bus.get("org.bluez", "/").GetManagedObjects()
                connected_target = None
                disconnected_candidate = None

                for path, interfaces in managed_objects.items():
                    dev = interfaces.get("org.bluez.Device1")
                    if not dev:
                        continue

                    name = str(dev.get("Name", ""))
                    mac = dev.get("Address")
                    if not mac or not self._is_target(name):
                        continue

                    if dev.get("Connected", False):
                        connected_target = (name, mac)
                        break
                    if disconnected_candidate is None:
                        disconnected_candidate = (path, name, mac)

                if connected_target:
                    name, mac = connected_target
                    if self._connected_mac != mac:
                        self._connected_mac = mac
                        self.logger.write(f"[INFO] Target already connected: {name} ({mac})")
                        self._set_pulseaudio_sink(mac)
                else:
                    if self._connected_mac:
                        self.logger.write(f"[WARN] Bluetooth device disconnected: {self._connected_mac}")
                        self._connected_mac = None

                    if disconnected_candidate:
                        path, name, mac = disconnected_candidate
                        try:
                            device = self.bus.get("org.bluez", path)
                            device.Connect()
                            self._connected_mac = mac
                            self.logger.write(f"[INFO] Connected with {name} ({mac})")
                            self._set_pulseaudio_sink(mac)
                        except Exception as exc:
                            self.logger.write(f"[WARN] Connection to {mac} failed: {exc}")
            except Exception as exc:
                self.logger.write(f"[WARN] Scan loop exception: {exc}")
            finally:
                if discovery_started:
                    try:
                        self.adapter.StopDiscovery()
                    except Exception:
                        pass

            self._stop_event.wait(self.scan_interval)

    def _set_pulseaudio_sink(self, mac):
        self.logger.write(f"Waiting on PulseAudio sink for {mac} ...")
        target_fragment = mac.replace(":", "_").lower()

        for _ in range(20):
            try:
                sinks = subprocess.run(
                    ["pactl", "list", "short", "sinks"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                self.logger.write(f"[WARN] pactl unavailable: {exc}")
                return

            for line in sinks.stdout.splitlines():
                if target_fragment not in line.lower():
                    continue
                fields = line.split()
                if len(fields) < 2:
                    continue

                sink_name = fields[1]
                try:
                    result = subprocess.run(
                        ["pactl", "set-default-sink", sink_name],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=5,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    self.logger.write(f"[WARN] Could not set PulseAudio sink '{sink_name}': {exc}")
                    return
                if result.returncode != 0:
                    self.logger.write(
                        f"[WARN] Could not set PulseAudio sink '{sink_name}': {result.stderr.strip()}"
                    )
                    return

                try:
                    inputs = subprocess.run(
                        ["pactl", "list", "short", "sink-inputs"],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=5,
                    )
                    for input_line in inputs.stdout.splitlines():
                        input_fields = input_line.split()
                        if input_fields:
                            subprocess.run(
                                ["pactl", "move-sink-input", input_fields[0], sink_name],
                                check=False,
                                timeout=5,
                            )
                except (OSError, subprocess.SubprocessError) as exc:
                    self.logger.write(f"[WARN] Could not move existing audio streams: {exc}")

                self.logger.write(f"[INFO] Audio transferred to Bluetooth device via '{sink_name}'.")
                return

            if self._stop_event.wait(1):
                return

        self.logger.write(f"[WARN] PulseAudio sink for {mac} not found.")

    def start(self):
        if self._thread and self._thread.is_alive():
            self.logger.write("[WARN] BluetoothService already running.")
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, name="bluetooth-scan", daemon=True)
        self._thread.start()
        self.logger.write("[INFO] BluetoothService thread started.")

    def stop(self):
        self.logger.write("[INFO] Stopping BluetoothService...")
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

        if self._connected_mac and self.bus:
            mac = self._connected_mac
            try:
                device = self.bus.get(
                    "org.bluez",
                    f"/org/bluez/hci0/dev_{mac.replace(':', '_')}",
                )
                device.Disconnect()
                self.logger.write(f"[INFO] Disconnected from {mac}")
            except Exception as exc:
                self.logger.write(f"[WARN] Disconnecting from {mac} failed: {exc}")
        self._connected_mac = None
        self.logger.write("[INFO] BluetoothService stopped.")

    def disconnect_all_targets(self):
        """Disconnect all currently connected Bluetooth devices."""
        if not self.bus:
            self.logger.write("[WARN] No D-Bus available, cannot disconnect any device.")
            return

        try:
            managed_objects = self.bus.get("org.bluez", "/").GetManagedObjects()
            disconnected = 0

            for path, interfaces in managed_objects.items():
                dev = interfaces.get("org.bluez.Device1")
                if not dev or not dev.get("Connected", False):
                    continue

                name = dev.get("Name", "Unknown")
                mac = dev.get("Address")
                try:
                    self.bus.get("org.bluez", path).Disconnect()
                    disconnected += 1
                    self.logger.write(f"[INFO] Disconnected from {name} ({mac})")
                except Exception as exc:
                    self.logger.write(f"[WARN] Disconnecting from {name} ({mac}) failed: {exc}")

            if disconnected == 0:
                self.logger.write("[INFO] No connected devices found.")
            else:
                self.logger.write(f"[INFO] {disconnected} device(s) disconnected.")
            self._connected_mac = None
        except Exception as exc:
            self.logger.write(f"[WARN] Error while disconnecting all targets: {exc}")
