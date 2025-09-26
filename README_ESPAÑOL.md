# 🌋 Estación Sísmica con Arduino + Python + Power BI

Proyecto académico y de demostración que implementa una **estación sísmica casera** utilizando un **Arduino UNO** con sensor **MPU6050** (acelerómetro/giroscopio). El sistema detecta movimientos, calcula intensidades, muestra gráficas en tiempo real y exporta registros para análisis en **Power BI**.

---

## ⚙️ Hardware utilizado
- Arduino UNO  
- Sensor MPU6050 (GY-521)  
- Buzzer activo  
- LED rojo (alarma)  
- Protoboard + cables Dupont  

---

## 💻 Software y dependencias
- **Arduino IDE** (librería `MPU6050` de Electronic Cats o Jeff Rowberg)  
- **Python 3.10+** con:  
  - `pyserial`  
  - `matplotlib`  
  - `pygame`  
- **Visual Studio Code** (con `launch.json` ya configurado en el repo)  
- **Power BI Desktop** (para análisis de datos exportados)

Instalar dependencias Python:
```bash
pip install -r requirements.txt
```
🚀 Funcionalidades principales

📈 Gráficas en tiempo real:

Movimiento por ejes (X/Y/Z con filtro pasa-altas)

Intensidad (|a|-1 g) y estado de alarma

Escala MMI (Mercalli Modificada) estimada a partir de PGA

🖥️ Interfaz interactiva (VS Code + matplotlib) con botones:

X/Y/Z

Intensidad

MMI

Vista de registros (tabla de últimos datos)

Exportar CSV (últimas N filas o últimos X segundos)

Vista general (las 3 gráficas a la vez)

Configuración (umbral MMI y sirena ON/OFF, botón Silencio)

Salir

🔔 Sirena sísmica real (sirena.mp3):

Se activa automáticamente cuando el MMI ≥ umbral (por defecto 9.0).

Suena en bucle por al menos 5 segundos.

Puede apagarse con el botón Silencio.

📊 Exportación CSV automática y manual:

Registro continuo de todos los datos.

Exportación de subconjuntos para análisis en Power BI.

▶️ Ejecución

Subir el código de Arduino (Estacion_Sismica_Proyecto_Fisica.ino).

Conectar el Arduino y verificar el puerto (ej: COM6).

Abrir VS Code y ejecutar con F5 (graficas_csv_menu.py).

📊 Integración con Power BI

Los archivos .csv generados pueden importarse directamente en Power BI.

Permite crear dashboards con tendencias, comparaciones por evento y alarmas.

📷 Demo

![Imagen de WhatsApp 2025-09-26 a las 08 13 43_c2348ea0](https://github.com/user-attachments/assets/f83d815c-19f8-4b97-805e-6fd5e9f874b2)


👤 Autor

Angel Moreno - 202425514
Proyecto académico y de demostración — Universidad Mesoamericana.
