# Container Gate OCR: install checklist for the site's IT

Prepare these before the install day. Questions: see [support.md](support.md).

## 1. The gate PC
- [ ] Windows 10 or 11, **64-bit**, on all day: sleep and hibernate **off** (*Settings → System →
      Power*). A desktop, or a laptop that stays plugged in.
- [ ] CPU, no graphics card needed:
  - one lane: an 8-core CPU (tested on an AMD Ryzen 7 5800U laptop);
  - two lanes where trucks often arrive at the same moment: a desktop 8-16 core CPU, or an NVIDIA
    graphics card (tell us, it is switched on in the settings).
- [ ] 16 GB memory recommended; at least 100 GB free on drive C: (records, photos and Excel files
      stay on this PC).
- [ ] A Windows user with **administrator rights** for the install. After that the gate runs by
      itself with nobody signed in.
- [ ] Windows Update restarts outside gate hours (*Settings → Windows Update → Advanced options →
      Active hours*). The gate starts by itself after every restart.
- [ ] Antivirus: allow the folder `C:\Program Files\Container Gate OCR` if it blocks or slows the app.

## 2. Cameras and recorder (NVR)
- [ ] The NVR's **IP address**, and a **username and password** that can view the live cameras
      (a view-only user is best). Hikvision NVRs are supported.
- [ ] Which NVR **channel** shows each gate lane.
- [ ] For each lane, a camera on the **number plate**: facing incoming trucks, 5-10 m away, zoomed
      so the plate is at least 150 pixels wide in the picture, no motion blur (an ANPR/LPR camera
      is ideal).
- [ ] For each lane, a camera on the **container**: it sees the container's rear doors or side from
      under about 10 m, so the code's letters are at least 25-30 pixels tall. Best where trucks stop
      at the barrier. A second container camera from the other side makes readings surer.
- [ ] At night the gate is lit, or the cameras' infrared reaches the plate and the container.

## 3. Network
- [ ] The gate PC is on the **same network as the NVR**, best with a cable to the NVR's switch.
      Test: on the PC, open the NVR's address in a browser and see its login page.
- [ ] A **fixed IP address** for the gate PC (a DHCP reservation on the router), so staff always
      find the app at the same address, e.g. `http://192.168.1.50:8000`.
- [ ] The PC's network is **Private** (*Settings → Network → Properties → Private network*) or a
      domain network. The installer opens TCP port **8000** on private and domain networks only,
      never on public ones.
- [ ] PCs and phones that open the app are on the same site network (Wi-Fi or cable).
- [ ] **Internet** on the gate PC (outbound HTTPS, port 443): every 15 minutes the app tells us it
      is working and picks up a renewed license key. Only the app's health is sent, never plates,
      container numbers or photos. If outbound traffic is blocked, allow our Control Center's
      address (we send it to you). Without internet the gate still works; renewed keys are then
      typed in.
- [ ] Do **not** open port 8000 to the internet. For access from outside the site, use a VPN.
- [ ] Remote support: AnyDesk on the gate PC, or another remote tool you allow.

## 4. Install day
1. Sign in to the gate PC as an administrator and run `ContainerGateOCR-site-<version>-setup.exe`.
   Windows shows our name as the publisher.
2. The installer copies the app, starts it, and opens `http://localhost:8000`.
3. The app's setup: choose the admin password, enter the NVR address and login, choose the gate
   camera and drag a box over where trucks pass. Lanes and more cameras: the **Cameras** page.
4. Send us the **machine code** from the **License** page; we send the license key to type in.
5. From a phone on the site Wi-Fi, open `http://<gate PC address>:8000` and sign in.
6. Restart the PC once and check that the app opens again without anyone signing in.

## Where things are
| What | Where |
|---|---|
| The app | `C:\Program Files\Container Gate OCR` |
| Records (database), photos, Excel files | `C:\Program Files\Container Gate OCR\logs\`: **back this folder up** |
| Settings, including the NVR password | `C:\Program Files\Container Gate OCR\cameras.json` |
| Logs for support | `logs\app.log` and `logs\service.log` in the app folder |
| Autostart | Task Scheduler: *Container Gate OCR* (at PC start, as SYSTEM) |
| Firewall | Windows Defender Firewall rule *Container Gate OCR* (TCP 8000, private and domain) |

Uninstalling (*Settings → Apps*) removes the app, the autostart and the firewall rule, and keeps
`logs\` and `cameras.json`. Delete them by hand only when the records are no longer needed.
