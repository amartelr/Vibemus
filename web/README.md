# 🎸 Vibemus — Dashboard de Armonía Musical & Guía de Improvisación

**Vibemus** es una aplicación web para aprender a improvisar sobre tus canciones. Gestiona tu biblioteca desde Google Sheets, detecta acordes y progresiones, muestra el Círculo de Quintas, genera con **Gemini** una guía de improvisación para cada canción y la lleva a un **mástil de guitarra interactivo** que te dice qué notas tocar sobre cada acorde.

---

## 🧭 Cómo improvisar sobre una canción (guía rápida)

La idea clave: **casi nunca cambias de escala entera**. Casi siempre tocas las mismas notas y solo cambias **a qué notas apuntas**. De vez en cuando cambia **una sola nota**.

Sigue estos tres niveles en orden. No pases al siguiente hasta que el anterior te salga cómodo.

### Nivel 1 — Una sola escala para toda la canción
1. Abre la canción y pulsa **Guía de Improvisación**.
2. En **Base**, deja la escala de la tonalidad (ej. `D Mayor / Jónica`) con **Fusionar** desactivado.
3. Toca solo con esas notas sobre toda la canción.
4. Termina tus frases en las notas **rojas** o **verdes**. No te quedes parado en las de **borde discontinuo**.

> Si te cuesta, empieza con la **Pentatónica** del chip de Base: no tiene notas que choquen.

### Nivel 2 — Apuntar a las notas de cada acorde
Las notas siguen siendo las mismas, pero cada acorde tiene sus propias notas "de reposo".

1. Pulsa el chip del acorde en la fila de chips de acordes bajo **Base** (ej. `Bm (vi)`), o usa **Anterior / Siguiente** para recorrer la progresión en orden.
2. Mira las notas **verdes**: son las del acorde que está sonando.
3. Cuando suene ese acorde, **acaba tus frases en una nota verde**.

Si al activar un acorde **no aparece ninguna nota azul ni con halo**, ese acorde usa exactamente las mismas notas que la base. No cambias nada en los dedos; solo cambias el objetivo.

### Nivel 3 — Cambiar la nota que cambia
Algunos acordes no pertenecen a la tonalidad. En ellos **una nota de la escala base se sustituye por otra**:

- 🔵 **Azul:** la nota que **dejas** de tocar mientras suena ese acorde.
- ⭕ **Halo dorado:** la nota **nueva** que la reemplaza. Normalmente está a un semitono (un traste) de la azul.

Truco práctico: busca la nota azul en el mástil y **muévela un traste** hasta la del halo. El resto de la escala no se toca.

---

## 🎨 Qué significa cada color del mástil

| Color | Significado | Qué hacer |
|---|---|---|
| 🔴 Rojo | Tónica del modo activo | Punto de partida y de reposo total |
| 🟢 Verde | Notas del acorde (1-3-5-7) | Acaba aquí tus frases: suena "resuelto" |
| 🟡 Dorado | Nota característica del modo | Tócala para que se oiga el color del modo (ej. #4 en Lidia, b7 en Mixolidia) |
| ◌ Borde discontinuo | Nota a evitar | Pasa por ella, pero no te quedes: choca a medio tono con una nota del acorde |
| ⚫ Negro | Resto de notas de la escala | Notas de paso y tensiones |
| ⭕ Halo dorado | *(solo en Fusionar)* Nota nueva respecto a la base | Es la que tienes que cambiar |
| 🔵 Azul | *(solo en Fusionar)* Nota que solo está en la base | Déjala mientras suene este acorde |

Con **Fusionar** activo, los colores y los grados se calculan **respecto al modo de destino**, es decir, al acorde que está sonando. Pasa el ratón por encima de una nota para ver su papel y haz clic para escucharla.

---

## 🎵 Ejemplo completo: Oscar Lang — *Liking All Your Posts*

**Tonalidad:** D Mayor · **Progresión:** `V - Imaj7 - vi - I - III - vi7` → `A - Dmaj7 - Bm - D - F# - Bm7`

**Escala base:** D Mayor → `D E F# G A B C#`

| Acorde | Modo que propone la guía | ¿Cambia alguna nota respecto a D Mayor? | Apunta a (verdes) | Tipo de cambio |
|---|---|---|---|---|
| **A** (V) | A Mixolidia | No, mismas notas | A, C#, E | Solo cambias el objetivo |
| **Dmaj7** (Imaj7) | D Lidia | **G → G#** | D, F#, A, C# | Color opcional |
| **Bm** (vi) | B Eólica | No, mismas notas | B, D, F# | Solo cambias el objetivo |
| **D** (I) | D Mayor | No | D, F#, A | Vuelves a casa |
| **F#** (III) | F# Frigia Dominante | **A → A#** | F#, A#, C#, E | **Obligatorio**: el acorde lleva A# |
| **Bm7** (vi7) | B Dórica | **G → G#** | B, D, F#, A | Color opcional |

**Cómo leerlo de forma sencilla:**
- Toca **D Mayor todo el rato**.
- Sobre **F#**, cambia **A por A#**. Si tocas la A, chocará con la A# del acorde. La A# es la 3ª de F# y "tira" hacia el Bm que viene después; resuélvela subiendo un semitono a B.
- Sobre **Dmaj7** y **Bm7**, *si quieres*, cambia **G por G#** para dar un color más brillante (Lidia y Dórica). Con G también funciona, solo que suena más "normal".
- En los acordes que no cambian nada (A, Bm, D), céntrate en acabar las frases en sus notas verdes.

---

## 🔁 Rutina de práctica recomendada

1. **Elige una zona del mástil** de unos 4 trastes (ej. trastes 2–5 o 9–12). No intentes usar todo el mástil a la vez.
2. **Nivel 1:** improvisa 5 minutos solo con la escala base.
3. **Bucle de dos acordes:** elige el acorde que cambia una nota y el siguiente (ej. `F# → Bm7`). Practica solo el cambio `A → A#` y resuelve en B.
4. **Recorre la progresión** con **Anterior / Siguiente** y, sin tocar, di en voz alta la nota verde a la que irías en cada acorde.
5. **Toca sobre la canción** (el vídeo si está enlazado) aplicando solo los cambios obligatorios. Añade los opcionales cuando ya te salgan.

**Atajos del visualizador:**
- **Grados / Notas:** usa *Grados* para entender intervalos (3, b7, #4…) y *Notas* para ubicarte en el mástil.
- **Ver todos:** desbloquea las 12 notas y todos los modos para explorar libremente fuera de lo que propone la canción.
- **Consejo** (en la tarjeta de transición): el comentario que la guía de IA dio para ese acorde.

---

## 🧩 Módulos de la aplicación

### Guía de Improvisación con IA (Gemini)
A partir de la tonalidad y la progresión (grados romanos como `I - IVmaj7 - V`), Gemini genera una guía en español con:
1. **Escala más segura:** la opción diatónica base, sus notas y por qué funciona.
2. **Versión rock/pop:** la pentatónica para solos directos.
3. **Enfoques por secciones:** una tabla acorde por acorde con el modo recomendado, las notas principales y un comentario.

La guía se genera **una sola vez** y se guarda en la columna `improvisation` de Google Sheets. Las siguientes veces el botón muestra **Ver Guía de Improvisación** sin volver a llamar a la API. Los modos de la tabla alimentan los chips de acordes del mástil.

### Visualizador de mástil (`fretboard.js`)
- Mástil SVG de 6 cuerdas en afinación estándar, 15 trastes y cejuela, con marcadores en los trastes 3, 5, 7, 9, 12 y 15.
- Colores por papel de cada nota (tabla de arriba), calculados con teoría acorde-escala.
- Modo **Fusionar / Transición Modal** para comparar la escala base con el modo de cada acorde.
- Sintetizador Web Audio: haz clic en cualquier nota para oírla.

---

## 🛠️ Arquitectura Técnica

Esta aplicación vive dentro del proyecto Vibemus (antes era el proyecto independiente `mysongs`):

```
Vibemus/
├── src/web/server.py             # Backend Flask: Google Sheets API, scrapers y endpoint Gemini
├── web/
│   ├── app.js                    # Lógica del frontend: estado global, renderizado, modales
│   ├── fretboard.js              # Motor de teoría musical y renderizado SVG del mástil
│   ├── index.html                # Estructura de paneles Bento, modales y controles
│   └── style.css                 # Sistema de diseño: temas oscuros, bezels, markdown y mástil
├── scripts/recalculate_skills.py # Recalcula la dificultad (Skill) de todas las canciones
├── scripts/start_web.sh          # Arranque con registro en data/web.log
├── .env                          # GEMINI_API_KEY — no se sube a git
└── config/web/                   # client_secret.json, token.json, youtube_token.json — no se suben a git
```

### Tecnologías
- **Backend:** Python 3 (Flask, Google API Client, Requests, Pandas, RapidFuzz).
- **IA:** Google Gemini API, nivel gratuito (`gemini-3-flash-preview`, con otros modelos Flash de respaldo).
- **Base de datos:** Google Sheets (`Songs` y `Archived`).
- **Frontend:** Vanilla JavaScript (ES6+), SVG, CSS3 con variables.
- **Audio:** Web Audio API.
- **Markdown:** `marked.js` para renderizar la guía.

---

## ⚙️ Instalación y Configuración

### 1. Requisitos
- Python 3.11 o superior.
- Clave de API de Google Gemini (gratis en [Google AI Studio](https://aistudio.google.com/app/apikey)).
- Hoja de Google Sheets con las columnas:
  `playlist`, `artist`, `title`, `chord`, `tonality`, `progression`, `complex`, `style`, `improvisation`.

### 2. Variables de entorno (`.env`)
```env
GEMINI_API_KEY=tu_api_key_de_gemini_aqui
```
El servidor solo lee el `.env` al arrancar: si cambias la clave, reinícialo.

### 3. Dependencias
Están en el `requirements.txt` del proyecto (`pip install -r requirements.txt`).

---

## 🖥️ Ejecución

```bash
vibemus web                 # alias: vibemus serve  (--port 8001, --no-reload)
# o bien
./scripts/start_web.sh
```

Abre **http://localhost:8000** en el navegador.
