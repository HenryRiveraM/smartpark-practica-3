# PF-01 — Lectura de distancia

## 1. Descripción

Esta prueba funcional tiene como objetivo verificar el correcto funcionamiento del sensor ultrasónico HC-SR04, comprobando que las distancias detectadas correspondan aproximadamente con las distancias reales de los objetos.

## 2. Objetivo

Comprobar que el sensor ultrasónico pueda medir distancias de 10 cm, 20 cm y 30 cm, mostrando las mediciones en el monitor serie del entorno de desarrollo.

## 3. Procedimiento

1. Conectar el sensor ultrasónico HC-SR04 al ESP32.
2. Ejecutar el programa y abrir el monitor serie.
3. Colocar un objeto a una distancia de 10 cm del sensor, utilizando una cinta métrica como referencia.
4. Observar las mediciones mostradas en el monitor serie.
5. Repetir el procedimiento colocando el objeto a 20 cm y 30 cm.
6. Realizar 10 repeticiones de la prueba para cada una de las distancias.
7. Registrar las distancias esperadas, las distancias medidas y el resultado de la detección del vehículo.

## 4. Resultados obtenidos

Se realizaron 10 pruebas, evaluando tres distancias diferentes.

| Distancia esperada | Distancia promedio medida |
|---|---:|
| 10 cm | 9.91 cm |
| 20 cm | 19.96 cm |
| 30 cm | 30.00 cm |

Los resultados muestran que las mediciones obtenidas son cercanas a las distancias reales establecidas.

### Resultados de detección

- A 10 cm: el sistema detectó correctamente la presencia de un vehículo en las 10 pruebas.
- A 20 cm: el sistema no detectó la presencia de un vehículo en las 10 pruebas.
- A 30 cm: el sistema no detectó la presencia de un vehículo en las 10 pruebas.

## 5. Evidencias

Se adjuntan fotografías que documentan la ejecución de las pruebas:

| Archivo | Descripción |
|---|---|
| `pf01-10cm.jpeg` | Ubicación del objeto a 10 cm. |
| `pf01-10cmResultado.jpeg` | Mediciones obtenidas a 10 cm en el monitor serie. |
| `pf01-20cm.jpeg` | Ubicación del objeto a 20 cm. |
| `pf01-20cmResultado.jpeg` | Mediciones obtenidas a 20 cm en el monitor serie. |
| `pf01-30cm.jpeg` | Ubicación del objeto a 30 cm. |
| `pf01-30cmResultado.jpeg` | Mediciones obtenidas a 30 cm en el monitor serie. |

## 6. Resultado de la prueba

**Estado: APROBADA.**

El sensor ultrasónico HC-SR04 realizó correctamente las mediciones de distancia en los tres escenarios evaluados. Las diferencias entre las distancias esperadas y las medidas fueron pequeñas, demostrando que el sensor proporciona lecturas adecuadas para el funcionamiento del sistema.

Asimismo, el sistema identificó correctamente la presencia de un vehículo a 10 cm y no registró detecciones a 20 cm ni a 30 cm, de acuerdo con el comportamiento esperado.