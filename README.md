1. Install Pi imager, PuTTY, WinSCP, Real VNC Viewer
2. install pi os(regacy, 32 bit) to the micro SD card with WIFI setting
   Edit the Wi-Fi setting info and enable SSH in customisation
4. Connect Putty
5. Install and Enable VNC to use real VNC Viewer
      sudo apt update
      sudo apt install -y realvnc-vnc-server
      sudo raspi-config  # → Interface Options → VNC → <Yes> → Finish
      sudo reboot
6. Move the program file with Win SCP to the pi OS
7. Use Real VNC Viwer to controll the PI os
8. See https://docs.keyestudio.com/projects/KS0314/en/latest/docs/KS0314.html for installing the driver of the mic
