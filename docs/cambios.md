# Registro de cambios (PSet 1 a PSet 4)

Los memos originales se conservan sin modificar en `docs/historial/`. Las correcciones quedan registradas aquí y se
incorporan al documento técnico del PSet 4 (`docs/PSet4_memo_Pozo_Rivas.pdf`).

Los PSets 2 y 3 no recibieron observaciones.

## 1. Observaciones del PSet 1

| # | Observación | Qué se cambió | Dónde |
|---|---|---|---|
| 1 | *Tres ideas (9):* "Identifica un riesgo específico del pronóstico de Rossmann. Que el modelo no supere una regla simple es un riesgo inherente a cualquier proyecto predictivo." | El riesgo principal de la Idea 1 pasa a ser específico de Rossmann: **el modelo no ve los eventos locales recientes**. Sus features de ventas usan un rezago de 42 días (el horizonte), así que un cambio en una tienda (apertura de un competidor, obras, cierre temporal) tarda semanas en reflejarse, mientras que el gerente lo conoce desde el primer día. La simulación lo confirmó: con un competidor inducido, el monitoreo tardó 2 lotes en detectar la caída. Respuesta: el gerente reporta esos eventos (sección 8.5) y el monitoreo vigila el WAPE por tipo de tienda (criterio de retirada 3). | Documento técnico, secciones 1 y 8; `notebooks/07_analisis_monitoreo.ipynb` |
| 2 | *Comparación y selección (9):* "Incluye la justificación de cada calificación de las Ideas 2 y 3." | Se agrega la justificación de cada calificación (tabla 1.1 de este archivo). | Este archivo, sección 1.1 |
| 3 | *Problema y formulación (9.5):* "Comprueba el supuesto de que mejorar el pronóstico permite asignar turnos de manera más eficiente. Esa relación no puede demostrarse únicamente con las ventas." | El supuesto se hace explícito y se mide con una aproximación: el **costo de turnos mal asignados** (PSet 3), que supone que la dotación necesaria es proporcional a las ventas y que quedarse corto cuesta el doble que pasarse (k = 2; se probó la sensibilidad con k = 0,5, 1 y 3 en el PSet 3). La comprobación con turnos reales queda para un piloto con grupo de control (sección 1.2). | Documento técnico, secciones 1, 9 y 10 |
| 4 | *Viabilidad del negocio (9.5):* "Define cómo obtendrías las horas de personal necesarias para calcular las ventas por hora y evaluar el beneficio del modelo." | Se define la fuente y el cálculo: horas trabajadas por tienda y día, tomadas del registro de asistencia de las tiendas piloto y de control, unidas con las ventas por tienda y fecha; ventas por hora de personal = ventas del día / horas trabajadas ese día (sección 1.2). | Documento técnico, sección 10 |
| 5 | *Riesgos (9):* "La entrevista a gerentes no comprueba que mejores pronósticos produzcan mejores turnos. Diseña una comparación cuantitativa entre las decisiones tomadas con ambos pronósticos." | Se reemplaza la entrevista por una comparación cuantitativa: el costo de turnos mal asignados de las decisiones tomadas con el pronóstico del modelo frente a las tomadas con la regla del gerente, **lote por lote** en la simulación. El modelo costó menos en los 8 lotes (0,148 frente a 0,259; 43 % menos). En la operación real, la misma comparación se hace en el piloto con ventas por hora de personal. | `notebooks/07_analisis_monitoreo.ipynb`, sección 3; documento técnico, sección 9 |

### 1.1 Justificación de las calificaciones de las Ideas 2 y 3 (observación 2)

Escala: Alto (3), Medio (2), Bajo (1).

| Criterio | Idea 2: Favorita | Idea 3: Demanda eléctrica en Ecuador |
|---|---|---|
| Valor de negocio | **Alto (3):** abastecer de más genera merma y abastecer de menos, ventas perdidas; ambos afectan directamente el margen. | **Alto (3):** en 2024 hubo cortes de hasta 14 horas diarias; anticipar la demanda tiene un alto valor social y económico. |
| Acceso a datos | **Alto (3):** dataset público y completo en Kaggle (2013–2017). | **Bajo (1):** CENACE no tiene una descarga pública confirmada. |
| Target | **Alto (3):** ventas diarias por tienda y familia de productos, una columna directa del dataset. | **Medio (2):** la demanda horaria nacional es un target claro, pero la de 2024 quedó distorsionada por los cortes (la demanda no servida no se observa). |
| Acción | **Medio (2):** la acción (fijar la cantidad a abastecer) existe, pero no se sabe cómo decide hoy Favorita, así que la acción y sus costos serían supuestos. | **Medio (2):** la acción (programar la generación y los cortes) existe, pero la decide el operador del sistema, fuera del alcance del proyecto. |
| Evaluación | **Medio (2):** se puede medir el error del pronóstico, pero sin conocer el proceso actual no hay una línea base de negocio ni costos de merma con qué comparar. | **Bajo (1):** no hay un pronóstico oficial con qué comparar. |
| Alcance | **Medio (2):** miles de series tienda × familia de productos, más que el target único por tienda de Rossmann. | **Bajo (1):** depende de conseguir los datos y de tratar la demanda no servida de 2024. |
| **Total** | **15** | **11** |

### 1.2 Piloto para comprobar el beneficio en turnos (observaciones 3 y 4)

- **Diseño:** tiendas piloto que arman los turnos con el pronóstico del modelo y tiendas de control que siguen con su método, emparejadas por tipo de tienda, surtido y nivel de ventas; durante al menos 6 semanas (un horizonte completo).
- **Datos:** horas trabajadas por tienda y día del registro de asistencia, unidas con las ventas por tienda y fecha.
- **Métricas:** ventas por hora de personal (métrica de negocio del PSet 1) y horas de más y de menos frente a la dotación necesaria; con ellas se estima el valor real de k.
- **Decisión:** se extiende el uso del pronóstico si las ventas por hora de personal de las tiendas piloto superan a las de control.

## 2. Decisiones actualizadas

| Decisión | Antes | Ahora | Motivo | Dónde |
|---|---|---|---|---|
| Métrica de negocio medible en el proyecto | Ventas por hora de personal, solo en un piloto posterior (PSet 1) | **Costo de turnos mal asignados (k = 2)** frente a la regla del gerente; ventas por hora de personal queda como métrica del piloto | Los datos no tienen horas de personal; el costo de turnos permite comparar las decisiones con ambos pronósticos (observaciones 3 a 5). Se introdujo en el PSet 3 y se usa en todo el PSet 4 | `src/pipeline.py` (`costo_turnos`), monitoreo, sección 9 |
| Umbral de decisión | Cadencia: cada semana el gerente recibe el pronóstico de seis semanas (PSet 1) | Además, la API traduce el pronóstico en una **decisión por tienda y día**: ajuste de la dotación frente a la regla del gerente; > +15 % reforzar turnos, < −15 % reducir turnos, entre ambos mantener el plan | La API debe devolver la acción del PSet 1. Con los datos disponibles se entrega el ajuste relativo y no un número de personas (falta la productividad por tienda) | `api/main.py` |
| Juicio humano | El gerente revisa y puede ajustar por eventos locales (PSet 1) | Se mantiene y se precisa: el gerente **confirma las reducciones de más de 15 %** y **reporta los eventos locales** | La subestimación la pagan empleados y clientes; el monitoreo tarda en detectar los eventos locales | `notebooks/07_analisis_monitoreo.ipynb`, sección 2.5 |
| Monitoreo previsto en el PSet 1 | Alerta si el WAPE por tienda supera al de la regla simple | Alertas por PSI, WAPE sobre la media de la CV + 2 desviaciones, modelo peor que la regla, calidad de datos y sistema; reentrenamiento con aprobación humana | Requisitos del PSet 4 | `monitoreo/`, `kestra/` |

El target, la unidad de predicción, el horizonte (1 a 42 días), la métrica técnica (WAPE), la línea base, la fuente de datos y el grano de la OBT (tienda × día) no cambiaron.

## 3. Ajustes técnicos al integrar los PSets 2 y 3 en `proyecto_final/`

| Cambio | Archivo | Motivo |
|---|---|---|
| `06_reproduccion.ipynb` del PSet 3 pasa a llamarse `05b_reproduccion.ipynb` (contenido sin cambios) | `notebooks/` | El número 06 corresponde a `06_simulacion_produccion.ipynb` del PSet 4 |
| La ingesta se mantiene en los 4 flujos del PSet 2 (`rossmann_ingest_raw`, `rossmann_transform`, `rossmann_backfill`, `rossmann_daily_pipeline`) en lugar de un único `ingesta.yml` | `kestra/` | Ya funcionaban y estaban probados; reescribirlos no aportaba nada |
| La llave de Snowflake se lee y se pasa en memoria (`private_key`) en lugar de la ruta del archivo | `src/datos.py`, `api/main.py` | Docker en Windows monta los archivos con permisos amplios y el conector los rechaza |
| La URI de MLflow se lee de `MLFLOW_TRACKING_URI` (por defecto `http://localhost:5000`) | `src/pipeline.py` | En los contenedores que lanza Kestra MLflow se llama `mlflow`, no `localhost` |
| MLflow usa el volumen `pset3_mlflow-data` del PSet 3 como volumen externo | `docker-compose.yml` | Conservar las 107 corridas y el Model Registry sin copiarlos |
| `weeks_since_promo2_start`, `months_since_competition_open` y `competition_status` se miden pero no disparan alertas de deriva | `monitoreo/deriva.py` | Falsas alarmas en lotes sin alterar (PSI 0,34 y 0,29): cambian con el tiempo por definición |
| El criterio de retirada 3 compara cada tipo de tienda con su propio WAPE de referencia, no con el WAPE general | `notebooks/07_analisis_monitoreo.ipynb` | Contra el WAPE general no detectaba al competidor (las tiendas tipo "a" son el 54 % de los datos) |
