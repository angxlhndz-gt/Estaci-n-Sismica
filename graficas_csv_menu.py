# graficas_csv_menu.py
# Lector robusto 115200 + registro CSV + menú con 8 botones:
# [X/Y/Z] [Intensidad] [MMI] [Registros] [Exportar tabla] [General] [Config] [Salir]
# - Export configurable: últimas N filas o últimos X segundos (prioriza segundos)
# - Vista "General": muestra X/Y/Z, Intensidad y MMI a la vez
# - Config: Umbral MMI y Sirena ON/OFF + botón Silencio
# - Sirena (sirena.mp3) suena en bucle cuando MMI >= umbral, con duración mínima de 5 s

import sys, time, math, os
from collections import deque
from datetime import datetime

import serial
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, TextBox

# ====== AUDIO (sirena) ======
# Requiere: pip install pygame
import pygame
pygame.mixer.init()
SIRENA_FILE = "sirena.mp3"
sirena_on = True          # habilitada (toggle en Config)
sirena_activa = False     # está sonando ahora
SIRENA_MIN_MS = 5000      # 5 s mínimo una vez activada
sirena_start_ms = 0       # marca temporal de inicio
mmi_umbral = 9.0          # configurable en Config

def now_ms():
    return int(time.time() * 1000)

def start_sirena():
    global sirena_activa, sirena_start_ms
    if sirena_on and not sirena_activa:
        try:
            pygame.mixer.music.load(SIRENA_FILE)
            pygame.mixer.music.play(loops=-1)
            sirena_activa = True
            sirena_start_ms = now_ms()
            print("[SIRENA] Activada 🚨")
        except Exception as e:
            print(f"[SIRENA] Error al reproducir: {e}")

def stop_sirena(force=False):
    """Detiene la sirena. Si force=False respeta mínimo de 5s."""
    global sirena_activa
    if sirena_activa:
        if not force:
            if now_ms() - sirena_start_ms < SIRENA_MIN_MS:
                return  # aún no cumple 5s
        pygame.mixer.music.stop()
        sirena_activa = False
        print("[SIRENA] Detenida ✋")

# ====== CONFIG UART/APP ======
PORT = sys.argv[1] if len(sys.argv) > 1 else "COM6"
BAUD = 115200
TIMEOUT = 0.2
STALL_SEC = 2.0
REFRESH_HZ = 10
WIN_SEC = 20
PRINT_HZ_ARDUINO = 5
MAXPTS = WIN_SEC * PRINT_HZ_ARDUINO

HP_SEC = 3
HP_N = max(1, int(HP_SEC * PRINT_HZ_ARDUINO))
PGA_WIN_SEC = 5
PGA_N = max(1, int(PGA_WIN_SEC * PRINT_HZ_ARDUINO))

RUN_TAG = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_NAME = f"registro_estacion_{RUN_TAG}.csv"

# ====== BUFFERS ======
t_ms  = deque(maxlen=MAXPTS)
ax    = deque(maxlen=MAXPTS); ay = deque(maxlen=MAXPTS); az = deque(maxlen=MAXPTS)
inten = deque(maxlen=MAXPTS); alarm = deque(maxlen=MAXPTS)

ax_raw = deque(maxlen=HP_N); ay_raw = deque(maxlen=HP_N); az_raw = deque(maxlen=HP_N)
ax_hp  = deque(maxlen=MAXPTS); ay_hp = deque(maxlen=MAXPTS); az_hp = deque(maxlen=MAXPTS)

inten_win = deque(maxlen=PGA_N)
mmi_vals  = deque(maxlen=MAXPTS)

TABLE_ROWS = 15  # filas visibles en tabla

def moving_mean(buf): return (sum(buf)/len(buf)) if buf else 0.0
def pga_to_mmi(pga_g):
    pga_cmps2 = max(1e-6, pga_g * 980.665)
    mmi = 3.66 * math.log10(pga_cmps2) - 1.66
    return max(1.0, min(12.0, mmi))

# ====== SERIAL ======
ser = serial.Serial()
ser.port = PORT; ser.baudrate = BAUD; ser.timeout = TIMEOUT
ser.rtscts = False; ser.dsrdtr = False
print(f"Abriendo {PORT} @ {BAUD} ...")
ser.open()
try:
    ser.setDTR(False); ser.setRTS(False)
except Exception:
    pass
time.sleep(0.5)
ser.reset_input_buffer()
print("Leyendo... (Ctrl+C para salir)")

# ====== CSV continuo ======
csv_file = open(CSV_NAME, "w", encoding="utf-8", newline="")
csv_file.write("run_tag,port,t_ms,ax_g,ay_g,az_g,intensidad_g,alarm\n")
csv_file.flush()
print(f"[CSV] Registrando en: {os.path.abspath(CSV_NAME)}")

# ====== UI ======
plt.ion()
fig = plt.figure(figsize=(12, 7))

# Área principal para gráficos/tablas/config
ax_plot = plt.axes([0.08, 0.18, 0.90, 0.73])

# Botones (fila inferior)
btn_xyz_ax = plt.axes([0.04, 0.08, 0.11, 0.06])
btn_int_ax = plt.axes([0.16, 0.08, 0.11, 0.06])
btn_mmi_ax = plt.axes([0.28, 0.08, 0.11, 0.06])
btn_tab_ax = plt.axes([0.40, 0.08, 0.11, 0.06])
btn_exp_ax = plt.axes([0.52, 0.08, 0.14, 0.06])
btn_gen_ax = plt.axes([0.67, 0.08, 0.11, 0.06])
btn_cfg_ax = plt.axes([0.79, 0.08, 0.11, 0.06])  # NUEVO: Config
btn_exit_ax= plt.axes([0.91, 0.08, 0.07, 0.06])

b_xyz = Button(btn_xyz_ax, "X/Y/Z")
b_int = Button(btn_int_ax, "Intensidad")
b_mmi = Button(btn_mmi_ax, "MMI")
b_tab = Button(btn_tab_ax, "Registros")
b_exp = Button(btn_exp_ax, "Exportar tabla")
b_gen = Button(btn_gen_ax, "General")
b_cfg = Button(btn_cfg_ax, "Config")
b_out = Button(btn_exit_ax, "Salir")

# Inputs Export (debajo, separados)
ax_rows_box = plt.axes([0.04, 0.01, 0.11, 0.045])  # Filas
ax_secs_box = plt.axes([0.20, 0.01, 0.11, 0.045])  # Segundos (más a la derecha)
tb_rows = TextBox(ax_rows_box, "Filas:", initial=str(TABLE_ROWS))
tb_secs = TextBox(ax_secs_box, "Segundos:", initial="")

# Inputs Config (ubicados arriba a la derecha dentro del área de controles inferiores)
ax_umbral_box = plt.axes([0.52, 0.01, 0.14, 0.045])   # Umbral MMI
ax_toggle_box = plt.axes([0.67, 0.01, 0.11, 0.045])   # Sirena ON/OFF
btn_sil_ax    = plt.axes([0.79, 0.01, 0.11, 0.045])   # Silencio

tb_umbral = TextBox(ax_umbral_box, "Umbral MMI:", initial=str(mmi_umbral))
tb_toggle = TextBox(ax_toggle_box, "Sirena:", initial="ON")
b_sil     = Button(btn_sil_ax, "Silencio")

# Estado de vista
view_mode = "xyz"  # 'xyz' | 'int' | 'mmi' | 'table' | 'general' | 'cfg'

# Líneas para vistas simples
line_x = line_y = line_z = None
line_i = line_a = None
line_m = None

# Ejes de la vista "General"
general_ax1 = general_ax2 = general_ax3 = None
g_line_x = g_line_y = g_line_z = None
g_line_i = g_line_a = None
g_line_m = None

def clear_axes():
    ax_plot.clear()
    ax_plot.grid(True)

def destroy_general_axes():
    global general_ax1, general_ax2, general_ax3
    global g_line_x, g_line_y, g_line_z, g_line_i, g_line_a, g_line_m
    for a in (general_ax1, general_ax2, general_ax3):
        if a is not None:
            a.remove()
    general_ax1 = general_ax2 = general_ax3 = None
    g_line_x = g_line_y = g_line_z = None
    g_line_i = g_line_a = None
    g_line_m = None

def setup_view_xyz():
    destroy_general_axes()
    clear_axes()
    ax_plot.set_title("Movimiento por eje (pasa-altas)")
    ax_plot.set_ylabel("g"); ax_plot.set_xlabel("t (ms)")
    global line_x, line_y, line_z
    (line_x,) = ax_plot.plot([], [], label="X (HP)")
    (line_y,) = ax_plot.plot([], [], label="Y (HP)")
    (line_z,) = ax_plot.plot([], [], label="Z (HP)")
    ax_plot.legend(loc="upper right")

def setup_view_int():
    destroy_general_axes()
    clear_axes()
    ax_plot.set_title("Intensidad (|a|-1 g) y Alarma")
    ax_plot.set_ylabel("g"); ax_plot.set_xlabel("t (ms)")
    global line_i, line_a
    (line_i,) = ax_plot.plot([], [], label="Intensidad")
    (line_a,) = ax_plot.plot([], [], label="Alarma (0/1)", linestyle=":")
    ax_plot.legend(loc="upper right")

def setup_view_mmi():
    destroy_general_axes()
    clear_axes()
    ax_plot.set_title(f"MMI estimada (PGA {PGA_WIN_SEC}s)")
    ax_plot.set_ylabel("MMI"); ax_plot.set_xlabel("t (ms)")
    global line_m
    (line_m,) = ax_plot.plot([], [], label="MMI (desde PGA)")
    ax_plot.set_ylim(1, 10)
    ax_plot.legend(loc="upper left")

def setup_view_table():
    destroy_general_axes()
    clear_axes()
    ax_plot.set_title("Registros recientes — tabla de muestra")
    ax_plot.axis("off")

def setup_view_general():
    ax_plot.clear(); ax_plot.axis("off")
    destroy_general_axes()
    bbox = ax_plot.get_position()
    left, width, h, pad = bbox.x0, bbox.width, bbox.height, 0.02
    sub_h = (h - 2*pad) / 3.0
    y3 = bbox.y0
    y2 = y3 + sub_h + pad
    y1 = y2 + sub_h + pad

    global general_ax1, general_ax2, general_ax3
    general_ax1 = fig.add_axes([left, y1, width, sub_h])
    general_ax2 = fig.add_axes([left, y2, width, sub_h])
    general_ax3 = fig.add_axes([left, y3, width, sub_h])

    general_ax1.set_title("X/Y/Z (pasa-altas)"); general_ax1.set_ylabel("g"); general_ax1.grid(True)
    general_ax2.set_title("Intensidad |a|-1 g y Alarma"); general_ax2.set_ylabel("g"); general_ax2.grid(True)
    general_ax3.set_title(f"MMI (PGA {PGA_WIN_SEC}s)"); general_ax3.set_ylabel("MMI"); general_ax3.set_xlabel("t (ms)")
    general_ax3.grid(True); general_ax3.set_ylim(1,10)

    global g_line_x, g_line_y, g_line_z, g_line_i, g_line_a, g_line_m
    (g_line_x,) = general_ax1.plot([], [], label="X (HP)")
    (g_line_y,) = general_ax1.plot([], [], label="Y (HP)")
    (g_line_z,) = general_ax1.plot([], [], label="Z (HP)")
    general_ax1.legend(loc="upper right")

    (g_line_i,) = general_ax2.plot([], [], label="Intensidad")
    (g_line_a,) = general_ax2.plot([], [], label="Alarma (0/1)", linestyle=":")
    general_ax2.legend(loc="upper right")

    (g_line_m,) = general_ax3.plot([], [], label="MMI (desde PGA)")
    general_ax3.legend(loc="upper left")

def setup_view_cfg():
    destroy_general_axes()
    ax_plot.clear(); ax_plot.axis("off")
    ax_plot.set_title("Configuración — Umbral y Sirena (usar cajas abajo)")
    ax_plot.text(0.02, 0.8, f"- Umbral actual: {mmi_umbral:.2f}", fontsize=11)
    ax_plot.text(0.02, 0.7, f"- Sirena: {'ON' if sirena_on else 'OFF'}", fontsize=11)
    ax_plot.text(0.02, 0.6,  "- Botón 'Silencio' apaga la sirena de inmediato", fontsize=11)

# Inicial: XYZ
setup_view_xyz()

# Handlers botones
def on_xyz(event):
    global view_mode
    view_mode = "xyz"; setup_view_xyz()

def on_int(event):
    global view_mode
    view_mode = "int"; setup_view_int()

def on_mmi(event):
    global view_mode
    view_mode = "mmi"; setup_view_mmi()

def on_tab(event):
    global view_mode
    view_mode = "table"; setup_view_table()

def on_general(event):
    global view_mode
    view_mode = "general"; setup_view_general()

def on_cfg(event):
    global view_mode
    view_mode = "cfg"; setup_view_cfg()

def on_export(event):
    rows_text = tb_rows.text.strip()
    secs_text = tb_secs.text.strip()
    try:
        n_rows = int(rows_text) if rows_text else TABLE_ROWS
        if n_rows <= 0: n_rows = TABLE_ROWS
    except ValueError:
        n_rows = TABLE_ROWS
    try:
        n_secs = float(secs_text) if secs_text else 0.0
        if n_secs < 0: n_secs = 0.0
    except ValueError:
        n_secs = 0.0

    if n_secs > 0 and len(t_ms) >= 1:
        t_from = t_ms[-1] - int(n_secs*1000)
        idxs = [i for i in range(len(t_ms)) if t_ms[i] >= t_from]
    else:
        start = max(0, len(t_ms) - n_rows)
        idxs = list(range(start, len(t_ms)))

    rows = [[t_ms[i], f"{ax[i]:.6f}", f"{ay[i]:.6f}", f"{az[i]:.6f}", f"{inten[i]:.6f}", alarm[i]] for i in idxs]
    export_name = f"tabla_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(export_name, "w", encoding="utf-8", newline="") as f:
        f.write("t_ms,ax_g,ay_g,az_g,intensidad_g,alarm\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    print(f"[Export] Guardado: {os.path.abspath(export_name)}  (filas={len(rows)})")

def on_silencio(event):
    stop_sirena(force=True)

def on_exit(event):
    plt.close(fig)

b_xyz.on_clicked(on_xyz)
b_int.on_clicked(on_int)
b_mmi.on_clicked(on_mmi)
b_tab.on_clicked(on_tab)
b_exp.on_clicked(on_export)
b_gen.on_clicked(on_general)
b_cfg.on_clicked(on_cfg)
b_out.on_clicked(on_exit)
b_sil.on_clicked(on_silencio)

def update_config_from_inputs():
    global mmi_umbral, sirena_on
    # Umbral
    try:
        mmi_umbral = float(tb_umbral.text.strip())
    except ValueError:
        mmi_umbral = 9.0
        tb_umbral.set_val(str(mmi_umbral))
    # Sirena ON/OFF
    sirena_on = tb_toggle.text.strip().upper() == "ON"
    # Si se apagó desde config, detener
    if not sirena_on:
        stop_sirena(force=True)

# ====== Redibujo ======
def redraw():
    if len(t_ms) < 2:
        fig.canvas.draw(); fig.canvas.flush_events()
        return

    t0, t1 = t_ms[0], t_ms[-1]

    if view_mode == "xyz":
        line_x.set_data(t_ms, ax_hp); line_y.set_data(t_ms, ay_hp); line_z.set_data(t_ms, az_hp)
        ax_plot.set_xlim(t0, t1)
        vals = list(ax_hp)+list(ay_hp)+list(az_hp)
        if vals:
            vmin, vmax = min(vals), max(vals)
            if vmin == vmax: vmin -= 0.05; vmax += 0.05
            ax_plot.set_ylim(vmin - 0.01, vmax + 0.01)

    elif view_mode == "int":
        line_i.set_data(t_ms, inten); line_a.set_data(t_ms, alarm)
        ax_plot.set_xlim(t0, t1)
        if inten:
            vmin, vmax = min(inten), max(inten)
            if vmin == vmax: vmin -= 0.1; vmax += 0.1
            ax_plot.set_ylim(vmin - 0.01, vmax + 0.01)

    elif view_mode == "mmi":
        line_m.set_data(t_ms, mmi_vals)
        ax_plot.set_xlim(t0, t1); ax_plot.set_ylim(1, 10)

    elif view_mode == "table":
        ax_plot.clear(); ax_plot.axis("off")
        n = len(t_ms); start = max(0, n - TABLE_ROWS)
        rows = []
        for i in range(start, n):
            rows.append([t_ms[i], f"{ax[i]:.3f}", f"{ay[i]:.3f}", f"{az[i]:.3f}", f"{inten[i]:.3f}", alarm[i]])
        col_labels = ["t_ms","ax_g","ay_g","az_g","Intensidad_g","Alarm"]
        table = ax_plot.table(cellText=rows, colLabels=col_labels, loc="center")
        table.scale(1, 1.3)
        ax_plot.set_title("Registros recientes — tabla de muestra")

    elif view_mode == "general":
        if any(a is None for a in (general_ax1, general_ax2, general_ax3)):
            setup_view_general()
        # X/Y/Z
        g_line_x.set_data(t_ms, ax_hp); g_line_y.set_data(t_ms, ay_hp); g_line_z.set_data(t_ms, az_hp)
        general_ax1.set_xlim(t0, t1)
        vals = list(ax_hp)+list(ay_hp)+list(az_hp)
        if vals:
            vmin, vmax = min(vals), max(vals)
            if vmin == vmax: vmin -= 0.05; vmax += 0.05
            general_ax1.set_ylim(vmin - 0.01, vmax + 0.01)
        # Intensidad
        g_line_i.set_data(t_ms, inten); g_line_a.set_data(t_ms, alarm)
        general_ax2.set_xlim(t0, t1)
        if inten:
            vmin, vmax = min(inten), max(inten)
            if vmin == vmax: vmin -= 0.1; vmax += 0.1
            general_ax2.set_ylim(vmin - 0.01, vmax + 0.01)
        # MMI
        g_line_m.set_data(t_ms, mmi_vals)
        general_ax3.set_xlim(t0, t1); general_ax3.set_ylim(1, 10)

    fig.canvas.draw(); fig.canvas.flush_events()

# ====== LOOP con watchdog ======
last_ok = time.time()
last_draw = time.time()

try:
    while plt.fignum_exists(fig.number):
        line = ser.readline().decode(errors="ignore").strip()
        if not line:
            if time.time() - last_ok > STALL_SEC:
                ser.reset_input_buffer()
                last_ok = time.time()
            time.sleep(0.003)
        else:
            if line.startswith("#"):
                pass
            else:
                parts = line.split(',')
                if len(parts) == 6:
                    try:
                        t    = int(parts[0]); x = float(parts[1]); y = float(parts[2]); z = float(parts[3])
                        ig   = float(parts[4]); alv = int(parts[5])
                    except ValueError:
                        pass
                    else:
                        # Buffers de datos
                        t_ms.append(t); ax.append(x); ay.append(y); az.append(z)
                        inten.append(ig); alarm.append(alv)

                        ax_raw.append(x); ay_raw.append(y); az_raw.append(z)
                        ax_hp.append(x - moving_mean(ax_raw))
                        ay_hp.append(y - moving_mean(ay_raw))
                        az_hp.append(z - moving_mean(az_raw))

                        inten_win.append(abs(ig))
                        pga_g = max(inten_win) if inten_win else 0.0
                        mmi_vals.append(pga_to_mmi(pga_g))

                        # Registro CSV continuo
                        csv_file.write(f"{RUN_TAG},{PORT},{t},{x:.6f},{y:.6f},{z:.6f},{ig:.6f},{alv}\n")
                        if int(time.time()*2) % 1 == 0:
                            csv_file.flush()

                        last_ok = time.time()
                else:
                    ser.reset_input_buffer()

        # Actualiza config y sirena
        update_config_from_inputs()
        if mmi_vals:
            m = mmi_vals[-1]
            if m >= mmi_umbral:
                start_sirena()
            else:
                stop_sirena(force=False)  # respeta mínimo 5s

        # Redibujo limitado
        if time.time() - last_draw >= 1.0/REFRESH_HZ:
            last_draw = time.time()
            redraw()

except KeyboardInterrupt:
    print("\nSaliendo...")

finally:
    try: ser.close()
    except: pass
    try: csv_file.flush(); csv_file.close()
    except: pass
    stop_sirena(force=True)
    plt.ioff()
    try: redraw(); plt.show()
    except: pass
    print(f"[CSV] Guardado en: {os.path.abspath(CSV_NAME)}")
