# PF-08 — Validación de código de vinculación

## 1. Descripción

Esta prueba funcional tiene como objetivo verificar que el sistema de Alexa valide correctamente los códigos de vinculación ingresados por el usuario, rechazando aquellos que sean incorrectos, hayan vencido o no estén autorizados.

## 2. Objetivo

Comprobar que el sistema impida la vinculación cuando se proporciona un código no válido y que mantenga sin cambios la vinculación existente.

## 3. Procedimiento

1. Abrir la skill de Alexa del sistema de parqueo inteligente.
2. Iniciar el proceso de vinculación cuando corresponda.
3. Introducir un código de vinculación incorrecto o vencido.
4. Observar la respuesta proporcionada por Alexa.
5. Verificar que el sistema rechace el código.
6. Comprobar que no se establezca una nueva vinculación ni se modifique la vinculación existente.
7. Evitar realizar intentos innecesarios durante la ejecución de la prueba.

## 4. Resultado esperado

Alexa debe rechazar el código y proporcionar el siguiente mensaje:

> "El código no es válido, caducó, no está autorizado o se agotaron los intentos. Solicita ayuda al administrador."

Además, el sistema debe mantener sin cambios la vinculación del usuario, evitando que un código incorrecto o vencido permita establecer una asociación no autorizada.

## 5. Evidencias

Se adjunta el siguiente archivo como evidencia de la ejecución de la prueba:

| Archivo | Descripción |
|---|---|
| `pf-08.mp4` | Video de evidencia de la prueba de validación del código de vinculación mediante Alexa. |

## 6. Resultado de la prueba

**Estado: PENDIENTE DE VALIDACIÓN.**

La prueba se considerará aprobada cuando se compruebe que Alexa rechaza correctamente los códigos incorrectos o vencidos, muestra el mensaje establecido y conserva sin modificaciones la vinculación del usuario.

