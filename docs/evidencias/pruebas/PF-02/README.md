# PF-02 — Detección de vehículos

## 1. Descripción

Esta prueba funcional tiene como objetivo verificar que el sistema detecte correctamente la presencia de un vehículo mediante el sensor ultrasónico HC-SR04, de acuerdo con el rango de detección establecido.

## 2. Objetivo

Comprobar que el sistema identifique la presencia de un vehículo cuando se encuentra dentro del rango de detección y que indique su ausencia cuando supera dicho límite.

## 3. Procedimiento

1. Conectar el sensor ultrasónico HC-SR04 al ESP32.
2. Ejecutar el programa y abrir el monitor serie.
3. Colocar un objeto a una distancia de 10 cm del sensor.
4. Verificar que el sistema indique la presencia de un vehículo.
5. Repetir el procedimiento colocando el objeto a 16 cm, 17 cm y 18 cm.
6. Observar si el sistema identifica correctamente la presencia o ausencia del vehículo en cada distancia.
7. Repetir el procedimiento hasta completar las 6 pruebas.
8. Registrar los resultados obtenidos y compararlos con los resultados esperados.

## 4. Resultados obtenidos

Se realizaron 6 pruebas, evaluando cuatro distancias diferentes.

| Distancia | Resultado esperado |
|---|---|
| 10 cm | Vehículo detectado: Sí |
| 16 cm | Vehículo detectado: Sí |
| 17 cm | Vehículo detectado: Sí |
| 18 cm | Vehículo detectado: No |

### Resumen de resultados

- **10 cm:** Las 6 pruebas detectaron correctamente la presencia del vehículo.
- **16 cm:** Las 6 pruebas detectaron correctamente la presencia del vehículo.
- **17 cm:** 4 pruebas detectaron correctamente el vehículo y 2 presentaron resultados incorrectos.
- **18 cm:** Las 6 pruebas indicaron correctamente que no había un vehículo dentro del rango de detección.

### Evaluación general

De los 24 resultados registrados (6 pruebas por 4 distancias), 22 fueron correctos y 2 incorrectos.

Esto representa un porcentaje de resultados correctos del 91,67 %.

## 5. Evidencias

Se adjunta el video `pf02.mp4`, que documenta la ejecución de las pruebas, mostrando la ubicación del objeto a diferentes distancias y los resultados visualizados en el monitor serie.

También se incluye el archivo `pf02.xlsx`, que contiene el registro de las seis pruebas realizadas y la comparación entre los resultados obtenidos y esperados.

## 6. Resultado de la prueba

**Estado: APROBADA CON OBSERVACIONES.**

El sistema identificó correctamente la presencia de vehículos a 10 cm y 16 cm, así como su ausencia a 18 cm.

Sin embargo, a una distancia de 17 cm se presentaron inconsistencias en 2 de las 6 pruebas realizadas. Esto indica que el límite de detección necesita una revisión para garantizar un comportamiento estable en distancias cercanas al umbral establecido.

En general, el sistema presentó un 91,67 % de resultados correctos, por lo que cumple con la mayoría de los escenarios evaluados, aunque se recomienda revisar el comportamiento en el límite de detección.